// Shared helpers for the player-side executables (launcher and builder).
// Win32 + C++17 only; no third-party code.
#pragma once
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#ifndef WINVER
#define WINVER 0x0A00
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <shlobj.h>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

// ---------------------------------------------------------------- strings
inline std::string narrow(const std::wstring& w) {
    if (w.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), int(w.size()), nullptr, 0, nullptr, nullptr);
    std::string s(size_t(n), '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.data(), int(w.size()), s.data(), n, nullptr, nullptr);
    return s;
}
inline std::wstring widen(const std::string& s) {
    if (s.empty()) return {};
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), int(s.size()), nullptr, 0);
    std::wstring w(size_t(n), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), int(s.size()), w.data(), n);
    return w;
}
inline std::string u8path(const fs::path& p) { return narrow(p.wstring()); }

inline std::string hexOf(const unsigned char* data, size_t n) {
    static const char* digits = "0123456789abcdef";
    std::string out;
    out.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { out += digits[data[i] >> 4]; out += digits[data[i] & 15]; }
    return out;
}

// ---------------------------------------------------------------- files
inline std::string readFile(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("Cannot read " + u8path(path));
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}
inline void writeFile(const fs::path& path, const std::string& data) {
    fs::create_directories(path.parent_path());
    fs::path temp = path;
    temp += L".tmp";
    {
        std::ofstream out(temp, std::ios::binary | std::ios::trunc);
        if (!out) throw std::runtime_error("Cannot write " + u8path(path));
        out.write(data.data(), std::streamsize(data.size()));
        if (!out) throw std::runtime_error("Cannot write " + u8path(path));
    }
    if (!MoveFileExW(temp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        throw std::runtime_error("Cannot replace " + u8path(path));
}

inline fs::path executablePath() {
    std::vector<wchar_t> buf(32768);
    DWORD n = GetModuleFileNameW(nullptr, buf.data(), DWORD(buf.size()));
    if (!n || n >= buf.size()) throw std::runtime_error("Cannot locate installation");
    return std::wstring(buf.data(), n);
}
inline fs::path userDataPath() {
    PWSTR path = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &path)))
        throw std::runtime_error("Cannot locate user data folder");
    fs::path result = fs::path(path) / L"DisruptorRecompiled";
    CoTaskMemFree(path);
    return result;
}

// ---------------------------------------------------------------- SHA-256
class Sha256 {
public:
    Sha256() {
        if (BCryptOpenAlgorithmProvider(&alg_, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0 ||
            BCryptCreateHash(alg_, &hash_, nullptr, 0, nullptr, 0, 0) < 0)
            throw std::runtime_error("SHA-256 is unavailable");
    }
    ~Sha256() {
        if (hash_) BCryptDestroyHash(hash_);
        if (alg_) BCryptCloseAlgorithmProvider(alg_, 0);
    }
    Sha256(const Sha256&) = delete;
    Sha256& operator=(const Sha256&) = delete;
    void update(const void* data, size_t n) {
        if (n && BCryptHashData(hash_, (PUCHAR)data, ULONG(n), 0) < 0) throw std::runtime_error("SHA-256 failed");
    }
    std::string hex() {
        unsigned char digest[32]{};
        if (BCryptFinishHash(hash_, digest, sizeof(digest), 0) < 0) throw std::runtime_error("SHA-256 failed");
        return hexOf(digest, sizeof(digest));
    }
private:
    BCRYPT_ALG_HANDLE alg_ = nullptr;
    BCRYPT_HASH_HANDLE hash_ = nullptr;
};
inline std::string sha256(const std::string& data) {
    Sha256 h;
    h.update(data.data(), data.size());
    return h.hex();
}
// Streams a file; progress receives (bytes done, bytes total) and may return false to cancel.
inline std::string sha256File(const fs::path& path,
                              const std::function<bool(uint64_t, uint64_t)>& progress = {}) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                              FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
    if (file == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot open " + u8path(path));
    std::unique_ptr<void, decltype(&CloseHandle)> guard(file, &CloseHandle);
    LARGE_INTEGER size{};
    GetFileSizeEx(file, &size);
    Sha256 h;
    std::vector<unsigned char> block(4 << 20);
    uint64_t done = 0;
    for (;;) {
        DWORD got = 0;
        if (!ReadFile(file, block.data(), DWORD(block.size()), &got, nullptr))
            throw std::runtime_error("Cannot read " + u8path(path));
        if (!got) break;
        h.update(block.data(), got);
        done += got;
        if (progress && !progress(done, uint64_t(size.QuadPart))) throw std::runtime_error("Cancelled");
    }
    return h.hex();
}

// PE images carry a link timestamp and a checksum; everything else must match.
inline std::string normalizedPeSha256(const fs::path& path) {
    std::string data = readFile(path);
    if (data.size() < 0x40) throw std::runtime_error("Not an executable: " + u8path(path));
    uint32_t pe = 0;
    memcpy(&pe, data.data() + 0x3c, 4);
    if (size_t(pe) + 24 + 68 > data.size() || data.compare(pe, 4, std::string("PE\0\0", 4)) != 0)
        throw std::runtime_error("Not an executable: " + u8path(path));
    memset(&data[pe + 8], 0, 4);        // COFF TimeDateStamp
    memset(&data[pe + 24 + 64], 0, 4);  // Optional header CheckSum
    return sha256(data);
}

inline uint32_t crc32(const unsigned char* data, size_t n) {
    static uint32_t table[256];
    static bool ready = false;
    if (!ready) {
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t c = i;
            for (int k = 0; k < 8; ++k) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[i] = c;
        }
        ready = true;
    }
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) c = table[(c ^ data[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

// ---------------------------------------------------------------- base64
inline std::string base64Encode(const std::string& in) {
    static const char* t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    size_t i = 0;
    for (; i + 2 < in.size(); i += 3) {
        uint32_t v = (uint8_t(in[i]) << 16) | (uint8_t(in[i + 1]) << 8) | uint8_t(in[i + 2]);
        out += t[v >> 18]; out += t[(v >> 12) & 63]; out += t[(v >> 6) & 63]; out += t[v & 63];
    }
    if (i + 1 == in.size()) {
        uint32_t v = uint8_t(in[i]) << 16;
        out += t[v >> 18]; out += t[(v >> 12) & 63]; out += "==";
    } else if (i + 2 == in.size()) {
        uint32_t v = (uint8_t(in[i]) << 16) | (uint8_t(in[i + 1]) << 8);
        out += t[v >> 18]; out += t[(v >> 12) & 63]; out += t[(v >> 6) & 63]; out += '=';
    }
    return out;
}
inline std::string base64Decode(const std::string& in) {
    auto value = [](char c) -> int {
        if (c >= 'A' && c <= 'Z') return c - 'A';
        if (c >= 'a' && c <= 'z') return c - 'a' + 26;
        if (c >= '0' && c <= '9') return c - '0' + 52;
        if (c == '+') return 62;
        if (c == '/') return 63;
        return -1;
    };
    std::string out;
    uint32_t acc = 0;
    int bits = 0;
    for (char c : in) {
        int v = value(c);
        if (v < 0) continue;
        acc = (acc << 6) | uint32_t(v);
        bits += 6;
        if (bits >= 8) { bits -= 8; out += char((acc >> bits) & 0xFF); }
    }
    return out;
}

// ---------------------------------------------------------------- JSON
// A small reader for the release recipe and the runtime's capture records.
struct Json {
    enum Kind { Null, Bool, Number, String, Array, Object } kind = Null;
    bool boolean = false;
    double number = 0;
    std::string text;  // string value, or the raw token of a number
    std::vector<Json> items;
    std::vector<std::pair<std::string, Json>> members;

    const Json* find(const std::string& key) const {
        for (auto& m : members) if (m.first == key) return &m.second;
        return nullptr;
    }
    const Json& operator[](const std::string& key) const {
        if (const Json* j = find(key)) return *j;
        throw std::runtime_error("Missing field: " + key);
    }
    const std::string& str() const {
        if (kind != String) throw std::runtime_error("Expected a string");
        return text;
    }
    long long integer() const {
        if (kind != Number) throw std::runtime_error("Expected a number");
        return std::stoll(text);
    }

    static Json parse(const std::string& s) {
        size_t pos = 0;
        Json j = value(s, pos);
        skip(s, pos);
        if (pos != s.size()) throw std::runtime_error("Trailing data in JSON");
        return j;
    }

private:
    static void skip(const std::string& s, size_t& p) {
        while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\r' || s[p] == '\n')) ++p;
    }
    static void expect(const std::string& s, size_t& p, char c) {
        skip(s, p);
        if (p >= s.size() || s[p] != c) throw std::runtime_error(std::string("Malformed JSON: expected ") + c);
        ++p;
    }
    static std::string string(const std::string& s, size_t& p) {
        expect(s, p, '"');
        std::string out;
        while (p < s.size() && s[p] != '"') {
            char c = s[p++];
            if (c != '\\') { out += c; continue; }
            if (p >= s.size()) break;
            char e = s[p++];
            switch (e) {
            case 'n': out += '\n'; break;
            case 't': out += '\t'; break;
            case 'r': out += '\r'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'u': {
                if (p + 4 > s.size()) throw std::runtime_error("Malformed JSON escape");
                unsigned cp = unsigned(std::stoul(s.substr(p, 4), nullptr, 16));
                p += 4;
                if (cp >= 0xD800 && cp < 0xDC00 && p + 6 <= s.size() && s[p] == '\\' && s[p + 1] == 'u') {
                    unsigned lo = unsigned(std::stoul(s.substr(p + 2, 4), nullptr, 16));
                    p += 6;
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                }
                if (cp < 0x80) out += char(cp);
                else if (cp < 0x800) { out += char(0xC0 | (cp >> 6)); out += char(0x80 | (cp & 63)); }
                else if (cp < 0x10000) { out += char(0xE0 | (cp >> 12)); out += char(0x80 | ((cp >> 6) & 63)); out += char(0x80 | (cp & 63)); }
                else { out += char(0xF0 | (cp >> 18)); out += char(0x80 | ((cp >> 12) & 63)); out += char(0x80 | ((cp >> 6) & 63)); out += char(0x80 | (cp & 63)); }
                break;
            }
            default: out += e;
            }
        }
        if (p >= s.size()) throw std::runtime_error("Unterminated JSON string");
        ++p;
        return out;
    }
    static Json value(const std::string& s, size_t& p) {
        skip(s, p);
        if (p >= s.size()) throw std::runtime_error("Unexpected end of JSON");
        Json j;
        char c = s[p];
        if (c == '{') {
            j.kind = Object;
            ++p;
            skip(s, p);
            if (p < s.size() && s[p] == '}') { ++p; return j; }
            for (;;) {
                std::string key = string(s, p);
                expect(s, p, ':');
                j.members.emplace_back(key, value(s, p));
                skip(s, p);
                if (p < s.size() && s[p] == ',') { ++p; continue; }
                expect(s, p, '}');
                return j;
            }
        }
        if (c == '[') {
            j.kind = Array;
            ++p;
            skip(s, p);
            if (p < s.size() && s[p] == ']') { ++p; return j; }
            for (;;) {
                j.items.push_back(value(s, p));
                skip(s, p);
                if (p < s.size() && s[p] == ',') { ++p; continue; }
                expect(s, p, ']');
                return j;
            }
        }
        if (c == '"') { j.kind = String; j.text = string(s, p); return j; }
        if (s.compare(p, 4, "true") == 0) { j.kind = Bool; j.boolean = true; p += 4; return j; }
        if (s.compare(p, 5, "false") == 0) { j.kind = Bool; p += 5; return j; }
        if (s.compare(p, 4, "null") == 0) { p += 4; return j; }
        size_t start = p;
        while (p < s.size() && (isdigit((unsigned char)s[p]) || s[p] == '-' || s[p] == '+' || s[p] == '.' || s[p] == 'e' || s[p] == 'E')) ++p;
        if (start == p) throw std::runtime_error("Malformed JSON value");
        j.kind = Number;
        j.text = s.substr(start, p - start);
        j.number = std::stod(j.text);
        return j;
    }
};

inline std::string jsonQuote(const std::string& s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (c < 0x20) { char buf[8]; snprintf(buf, sizeof buf, "\\u%04x", c); out += buf; }
            else out += char(c);
        }
    }
    return out + "\"";
}

// ---------------------------------------------------------------- processes
// Quotes one argument so the MSVCRT/MinGW argv parser reproduces it exactly.
inline std::wstring quoteArg(const std::wstring& arg) {
    if (!arg.empty() && arg.find_first_of(L" \t\n\v\"") == std::wstring::npos) return arg;
    std::wstring out = L"\"";
    for (size_t i = 0;; ++i) {
        size_t slashes = 0;
        while (i < arg.size() && arg[i] == L'\\') { ++i; ++slashes; }
        if (i == arg.size()) { out.append(slashes * 2, L'\\'); break; }
        if (arg[i] == L'"') { out.append(slashes * 2 + 1, L'\\'); out += L'"'; }
        else { out.append(slashes, L'\\'); out += arg[i]; }
    }
    return out + L"\"";
}
inline std::wstring commandLine(const std::vector<std::wstring>& args) {
    std::wstring cmd;
    for (auto& a : args) { if (!cmd.empty()) cmd += L' '; cmd += quoteArg(a); }
    return cmd;
}

// Environment block with every inherited PSX_/DISRUPTOR_/SDL_ variable removed and
// the given overrides applied. Keys compare case-insensitively, as Windows does.
inline std::wstring environmentBlock(const std::vector<std::pair<std::wstring, std::wstring>>& set,
                                     bool dropGameVariables = true) {
    std::map<std::wstring, std::wstring> vars;  // upper-case key -> "Key=Value"
    auto upper = [](std::wstring s) { CharUpperBuffW(s.data(), DWORD(s.size())); return s; };
    if (wchar_t* env = GetEnvironmentStringsW()) {
        for (wchar_t* p = env; *p; p += wcslen(p) + 1) {
            std::wstring entry = p;
            size_t eq = entry.find(L'=', 1);
            if (eq == std::wstring::npos) continue;
            std::wstring key = upper(entry.substr(0, eq));
            if (dropGameVariables && (key.rfind(L"PSX_", 0) == 0 || key.rfind(L"DISRUPTOR_", 0) == 0 ||
                                      key.rfind(L"SDL_", 0) == 0))
                continue;
            vars[key] = entry;
        }
        FreeEnvironmentStringsW(env);
    }
    for (auto& kv : set) {
        if (kv.second.empty()) vars.erase(upper(kv.first));
        else vars[upper(kv.first)] = kv.first + L"=" + kv.second;
    }
    std::wstring block;
    for (auto& kv : vars) { block += kv.second; block += L'\0'; }
    block += L'\0';
    return block;
}

// A child process inside a kill-on-close job, with stdout+stderr merged into a pipe.
class Child {
public:
    Child() = default;
    Child(const Child&) = delete;
    Child& operator=(const Child&) = delete;
    ~Child() { kill(); close(); }

    void start(const std::vector<std::wstring>& args, const fs::path& cwd, const std::wstring& env,
               bool capture = true, DWORD priority = 0) {
        SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
        HANDLE writeEnd = nullptr;
        if (capture) {
            if (!CreatePipe(&read_, &writeEnd, &sa, 0)) throw std::runtime_error("Cannot create pipe");
            SetHandleInformation(read_, HANDLE_FLAG_INHERIT, 0);
        } else {
            writeEnd = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr);
        }
        HANDLE input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr);
        job_ = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job_, JobObjectExtendedLimitInformation, &limits, sizeof(limits));
        STARTUPINFOW si{sizeof(si)};
        si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        si.hStdOutput = writeEnd;
        si.hStdError = writeEnd;
        si.hStdInput = input;
        std::wstring cmd = commandLine(args);
        PROCESS_INFORMATION pi{};
        BOOL ok = CreateProcessW(args[0].c_str(), cmd.data(), nullptr, nullptr, TRUE,
                                 CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED | priority,
                                 env.empty() ? nullptr : (LPVOID)env.c_str(),
                                 cwd.empty() ? nullptr : cwd.c_str(), &si, &pi);
        DWORD error = GetLastError();
        CloseHandle(writeEnd);
        CloseHandle(input);
        if (!ok) throw std::runtime_error("Cannot start " + narrow(args[0]) + " (error " + std::to_string(error) + ")");
        AssignProcessToJobObject(job_, pi.hProcess);
        ResumeThread(pi.hThread);
        CloseHandle(pi.hThread);
        process_ = pi.hProcess;
    }
    // Reads whatever output is available without blocking.
    std::string poll() {
        std::string out;
        if (!read_) return out;
        DWORD avail = 0;
        while (PeekNamedPipe(read_, nullptr, 0, nullptr, &avail, nullptr) && avail) {
            std::string chunk(avail, '\0');
            DWORD got = 0;
            if (!ReadFile(read_, chunk.data(), avail, &got, nullptr) || !got) break;
            out.append(chunk.data(), got);
        }
        return out;
    }
    bool finished() const { return !process_ || WaitForSingleObject(process_, 0) == WAIT_OBJECT_0; }
    DWORD exitCode() const {
        DWORD code = 1;
        if (process_) GetExitCodeProcess(process_, &code);
        return code;
    }
    HANDLE handle() const { return process_; }
    void kill() {
        if (job_) TerminateJobObject(job_, 1);
        if (process_) WaitForSingleObject(process_, 10000);
    }
    void close() {
        if (read_) { CloseHandle(read_); read_ = nullptr; }
        if (process_) { CloseHandle(process_); process_ = nullptr; }
        if (job_) { CloseHandle(job_); job_ = nullptr; }
    }

private:
    HANDLE process_ = nullptr, read_ = nullptr, job_ = nullptr;
};
