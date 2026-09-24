// DisruptorBuilder: builds the native game on the player's PC from their own disc.
//
// The installer ships no game code. This program extracts the original executable
// from the verified disc image, regenerates the C translation with the bundled
// recompiler, compiles and links it with the bundled compiler, then boots the new
// build once (hidden, silent) to compile the kernel code the game installs at boot.
// Every stage is checked against the fingerprints of the tested release (kit/recipe.json),
// so the result is the same program that was tested, or the build stops.
//
// Output lines for the installer/launcher: "PROGRESS <0-100> <text>", "ERROR <text>".
#include "common.hpp"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <set>
#include <thread>

namespace {

struct BuildError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct Context {
    fs::path root, kit, game, work, disc, logPath;
    std::ofstream log;
    Json recipe;
    int jobs = 0;
    bool keepWork = false;
};
Context ctx;

void logLine(const std::string& line) {
    if (ctx.log) { ctx.log << line << "\n"; ctx.log.flush(); }
}
void progress(int percent, const std::string& text) {
    printf("PROGRESS %d %s\n", percent, text.c_str());
    fflush(stdout);
    logLine("== " + std::to_string(percent) + "% " + text);
}
[[noreturn]] void fail(const std::string& message) { throw BuildError(message); }

std::wstring systemDir() {
    wchar_t buf[MAX_PATH]{};
    GetSystemDirectoryW(buf, MAX_PATH);
    return buf;
}
std::wstring windowsDir() {
    wchar_t buf[MAX_PATH]{};
    GetWindowsDirectoryW(buf, MAX_PATH);
    return buf;
}
fs::path toolchainBin() { return ctx.kit / L"toolchain" / L"bin"; }
// Only the bundled toolchain and Windows itself are visible to child processes, so a
// developer toolchain or foreign MinGW DLLs on the player's PATH cannot interfere.
std::wstring toolPath() { return toolchainBin().wstring() + L";" + systemDir() + L";" + windowsDir(); }
std::wstring toolEnv(std::vector<std::pair<std::wstring, std::wstring>> extra = {}) {
    std::wstring temp = (ctx.work / L"tmp").wstring();
    extra.insert(extra.begin(), {{L"PATH", toolPath()}, {L"TEMP", temp}, {L"TMP", temp}});
    return environmentBlock(extra);
}

// GCC and binutils use the ANSI code page for file names. A path with characters
// outside it (for example a user name in another script) gets its 8.3 short form.
bool ansiSafe(const std::wstring& s) {
    BOOL lossy = FALSE;
    int n = WideCharToMultiByte(CP_ACP, WC_NO_BEST_FIT_CHARS, s.c_str(), -1, nullptr, 0, nullptr, &lossy);
    return n > 0 && !lossy;
}
fs::path toolSafe(const fs::path& path) {
    if (ansiSafe(path.wstring())) return path;
    std::vector<wchar_t> buf(32768);
    DWORD n = GetShortPathNameW(path.c_str(), buf.data(), DWORD(buf.size()));
    if (n && n < buf.size() && ansiSafe(buf.data())) return fs::path(buf.data());
    fail("The installation folder name contains characters the build tools cannot use. "
         "Install into a folder such as C:\\Games\\Disruptor Recompiled.");
}

// Runs one tool to completion, logging its output. Returns the output.
std::string run(const std::vector<std::wstring>& args, const fs::path& cwd, const std::wstring& env,
                const std::string& what) {
    logLine("$ " + narrow(commandLine(args)));
    Child child;
    child.start(args, cwd, env);
    std::string output;
    while (!child.finished()) {
        output += child.poll();
        WaitForSingleObject(child.handle(), 50);
    }
    output += child.poll();
    logLine(output);
    if (child.exitCode() != 0)
        fail(what + " failed (exit " + std::to_string(child.exitCode()) + "). See the build log.");
    return output;
}

void expectHash(const fs::path& path, const std::string& expected, const std::string& what) {
    if (!fs::is_regular_file(path)) fail(what + " is missing: " + u8path(path.filename()));
    std::string actual = sha256File(path);
    if (actual != expected)
        fail(what + " does not match the tested release (" + u8path(path.filename()) + ").");
}

// ------------------------------------------------------------------ 1. disc
void verifyDisc() {
    const Json& disc = ctx.recipe["disc"];
    if (!fs::is_regular_file(ctx.disc)) fail("The disc image is missing. Run Setup again and select your disc image.");
    if (uint64_t(fs::file_size(ctx.disc)) != uint64_t(disc["size"].integer()))
        fail("The disc image is not the supported Disruptor USA (SLUS-00224) raw dump.");
    int last = -1;
    std::string hash = sha256File(ctx.disc, [&](uint64_t done, uint64_t total) {
        int pct = int(done * 8 / (total ? total : 1));
        if (pct != last) { last = pct; progress(1 + pct, "Verifying your disc image"); }
        return true;
    });
    if (hash != disc["sha256"].str())
        fail("The disc image does not match the supported Disruptor USA release.");
}

// ------------------------------------------------------------------ 2. executable
// Raw MODE2/2352 sectors; Form 1 user data starts 24 bytes into each sector.
class RawDisc {
public:
    explicit RawDisc(const fs::path& path) : in_(path, std::ios::binary) {
        if (!in_) fail("Cannot open the disc image.");
    }
    std::string sector(uint32_t lba) {
        std::string data(2048, '\0');
        in_.seekg(std::streamoff(uint64_t(lba) * 2352 + 24));
        in_.read(data.data(), 2048);
        if (!in_) fail("The disc image is truncated.");
        return data;
    }
    std::string read(uint32_t lba, uint32_t size) {
        std::string out;
        for (uint32_t i = 0; out.size() < size; ++i) out += sector(lba + i);
        out.resize(size);
        return out;
    }
private:
    std::ifstream in_;
};
uint32_t le32(const std::string& s, size_t at) {
    uint32_t v = 0;
    memcpy(&v, s.data() + at, 4);
    return v;
}

void extractExecutable() {
    progress(10, "Reading the game program from your disc");
    const Json& exe = ctx.recipe["exe"];
    RawDisc disc(ctx.disc);
    std::string pvd = disc.sector(16);
    if (pvd[0] != 1 || pvd.compare(1, 5, "CD001") != 0) fail("The disc image has no readable file system.");
    uint32_t rootLba = le32(pvd, 156 + 2), rootSize = le32(pvd, 156 + 10);
    std::string dir = disc.read(rootLba, rootSize);
    std::string want = exe["iso_name"].str();
    for (size_t sector = 0; sector < dir.size(); sector += 2048) {
        for (size_t at = sector; at < sector + 2048 && at < dir.size();) {
            uint8_t len = uint8_t(dir[at]);
            if (!len) break;
            uint8_t nameLen = uint8_t(dir[at + 32]);
            std::string name = dir.substr(at + 33, nameLen);
            if (_stricmp(name.c_str(), want.c_str()) == 0) {
                std::string data = disc.read(le32(dir, at + 2), le32(dir, at + 10));
                if (sha256(data) != exe["sha256"].str())
                    fail("The game program on this disc is not the supported SLUS-00224 revision.");
                writeFile(ctx.work / L"input" / widen(exe["file"].str()), data);
                return;
            }
            at += len;
        }
    }
    fail("The game program was not found on this disc image.");
}

// ------------------------------------------------------------------ 3. function seeds
// Same first-pass list the project's disc preparation writes: the entry point plus
// every direct call target inside the program, followed by the project's extra seeds.
void writeSeeds() {
    const Json& seeds = ctx.recipe["seeds"];
    std::string exe = readFile(ctx.work / L"input" / widen(ctx.recipe["exe"]["file"].str()));
    if (exe.size() < 0x800 || exe.compare(0, 8, "PS-X EXE") != 0) fail("The extracted program is not a PS-X EXE.");
    uint32_t pc0 = le32(exe, 0x10), load = le32(exe, 0x18), textSize = le32(exe, 0x1C);
    std::string text = exe.substr(0x800, textSize);
    std::set<uint32_t> found{pc0 & ~3u};
    uint32_t lo = load, hi = load + uint32_t(text.size());
    for (size_t off = 0; off + 3 < text.size(); off += 4) {
        uint32_t w = le32(text, off);
        if ((w >> 26) != 3) continue;  // JAL
        uint32_t pc = load + uint32_t(off);
        uint32_t target = (pc & 0xF0000000u) | ((w & 0x03FFFFFFu) << 2);
        if (target >= lo && target < hi && (target & 3) == 0) found.insert(target);
    }
    // probe_disc.py writes its part with CRLF line ends; build.ps1 appends the extra
    // seeds file unchanged plus a CRLF.
    char buf[160];
    std::string out = "# Auto-scanned JAL targets (+ entry) from " + ctx.recipe["exe"]["file"].str() + "\r\n";
    snprintf(buf, sizeof buf, "# entry=0x%08x load=0x%08x text_size=0x%x\r\n", pc0, load, textSize);
    out += buf;
    out += "# First-pass only \xE2\x80\x94 add overlay / runtime discoveries as you decomp.\r\n";
    for (uint32_t a : found) { snprintf(buf, sizeof buf, "0x%08X\r\n", a); out += buf; }
    out += readFile(ctx.kit / widen(seeds["extra"].str()));
    out += "\r\n";
    if (sha256(out) != seeds["sha256"].str()) fail("The function list differs from the tested release.");
    writeFile(ctx.work / L"input" / L"functions.txt", out);
}

// ------------------------------------------------------------------ 4. translation
void recompile() {
    progress(13, "Translating the game program to C");
    fs::copy_file(ctx.root / L"game.toml", ctx.work / L"game.toml", fs::copy_options::overwrite_existing);
    fs::create_directories(ctx.work / L"psxrecomp" / L"bios");
    fs::copy_file(ctx.kit / L"psxrecomp" / L"bios" / L"OpenBIOS.toml", ctx.work / L"psxrecomp" / L"bios" / L"OpenBIOS.toml",
                  fs::copy_options::overwrite_existing);
    run({(ctx.kit / L"recompiler" / L"psxrecomp-game.exe").wstring(), L"--config", L"game.toml"}, ctx.work, toolEnv(),
        "The recompiler");
    progress(17, "Checking the translation");
    for (auto& file : ctx.recipe["recompile"]["generated"].members)
        expectHash(ctx.work / L"generated" / widen(file.first), file.second.str(), "Translated code");
}

// ------------------------------------------------------------------ 5. compile
int jobCount() {
    if (ctx.jobs > 0) return ctx.jobs;
    SYSTEM_INFO si{};
    GetSystemInfo(&si);
    MEMORYSTATUSEX mem{sizeof(mem)};
    GlobalMemoryStatusEx(&mem);
    // The largest translation units need about 1 GB each at -O3.
    int byMemory = int((mem.ullAvailPhys >> 20) / 1100);
    return std::clamp(std::min(int(si.dwNumberOfProcessors), byMemory), 1, 16);
}

void compileGame() {
    const Json& compile = ctx.recipe["compile"];
    const auto& units = compile["units"].items;
    fs::create_directories(ctx.work / L"obj");
    // Flags exactly as the tested build used them; @KIT/ and @WORK/ stand for the
    // kit and work folders of this installation.
    auto profileArgs = [&](const std::string& name) {
        std::vector<std::wstring> args{(toolchainBin() / L"gcc.exe").wstring()};
        for (auto& a : compile["profiles"][name].items) {
            std::wstring arg = widen(a.str());
            for (auto [token, dir] : {std::pair<std::wstring, fs::path>{L"@KIT/", ctx.kit}, {L"@WORK/", ctx.work}}) {
                size_t at = arg.find(token);
                if (at != std::wstring::npos)
                    arg = arg.substr(0, at) + (dir / fs::path(arg.substr(at + token.size())).make_preferred()).wstring();
            }
            args.push_back(arg);
        }
        return args;
    };
    std::wstring env = toolEnv();

    int jobs = jobCount();
    logLine("parallel compile jobs: " + std::to_string(jobs));
    struct Running { std::unique_ptr<Child> child; size_t unit; std::string output; };
    std::vector<Running> running;
    size_t next = 0, done = 0;
    progress(20, "Compiling the game (" + std::to_string(units.size()) + " parts, " + std::to_string(jobs) + " at a time)");
    while (done < units.size()) {
        while (running.size() < size_t(jobs) && next < units.size()) {
            const Json& unit = units[next];
            auto args = profileArgs(unit["profile"].str());
            args.push_back(L"-c");
            args.push_back((ctx.work / L"generated" / widen(unit["source"].str())).wstring());
            args.push_back(L"-o");
            args.push_back((ctx.work / L"obj" / widen(unit["object"].str())).wstring());
            logLine("$ " + narrow(commandLine(args)));
            Running r{std::make_unique<Child>(), next, {}};
            r.child->start(args, ctx.work, env, true, BELOW_NORMAL_PRIORITY_CLASS);
            running.push_back(std::move(r));
            ++next;
        }
        std::vector<HANDLE> handles;
        for (auto& r : running) handles.push_back(r.child->handle());
        WaitForMultipleObjects(DWORD(handles.size()), handles.data(), FALSE, 100);
        for (auto it = running.begin(); it != running.end();) {
            it->output += it->child->poll();
            if (!it->child->finished()) { ++it; continue; }
            it->output += it->child->poll();
            if (!it->output.empty()) logLine(it->output);
            const Json& unit = units[it->unit];
            if (it->child->exitCode() != 0)
                fail("Compiling " + unit["source"].str() + " failed. See the build log.");
            expectHash(ctx.work / L"obj" / widen(unit["object"].str()), unit["sha256"].str(), "Compiled code");
            ++done;
            progress(20 + int(done * 50 / units.size()),
                     "Compiling the game (" + std::to_string(done) + " of " + std::to_string(units.size()) + ")");
            it = running.erase(it);
        }
    }
}

// ------------------------------------------------------------------ 6. link
std::wstring rspPath(const fs::path& p) {
    std::wstring s = p.wstring();
    std::replace(s.begin(), s.end(), L'\\', L'/');  // GCC response files treat backslash as an escape
    return L"\"" + s + L"\"";
}

void linkGame() {
    progress(71, "Linking the game");
    const Json& link = ctx.recipe["link"];
    std::wstring rsp;
    for (auto& input : link["inputs"].items) {
        const std::string& s = input.str();
        rsp += rspPath(s[0] == '@' ? ctx.work / L"obj" / widen(s.substr(1)) : ctx.kit / widen(s)) + L"\n";
    }
    for (auto& lib : link["libs"].items) {
        const std::string& s = lib.str();
        rsp += (s[0] == '-' ? widen(s) : rspPath(ctx.kit / widen(s))) + L"\n";
    }
    // GCC reads response files in the ANSI code page; toolSafe() checked the paths fit it.
    int n = WideCharToMultiByte(CP_ACP, 0, rsp.c_str(), int(rsp.size()), nullptr, 0, nullptr, nullptr);
    std::string ansi(size_t(n), '\0');
    WideCharToMultiByte(CP_ACP, 0, rsp.c_str(), int(rsp.size()), ansi.data(), n, nullptr, nullptr);
    writeFile(ctx.work / L"link.rsp", ansi);
    fs::path out = ctx.work / L"DisruptorRecompiled.exe";
    std::vector<std::wstring> args{(toolchainBin() / L"g++.exe").wstring()};
    for (auto& a : link["args"].items) args.push_back(widen(a.str()));
    args.push_back(L"@" + (ctx.work / L"link.rsp").wstring());
    args.push_back(L"-o");
    args.push_back(out.wstring());
    run(args, ctx.work, toolEnv(), "Linking");
    if (normalizedPeSha256(out) != link["normalized_sha256"].str())
        fail("The linked game differs from the tested release.");
    fs::create_directories(ctx.game);
    if (!MoveFileExW(out.c_str(), (ctx.game / L"DisruptorRecompiled.exe").c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED | MOVEFILE_WRITE_THROUGH))
        fail("Cannot place the game in the installation folder. Close the game and try again.");
}

// ------------------------------------------------------------------ 7. kernel code
// Python's json.dumps default layout, which the capture files use.
std::string dumpPython(const Json& j) {
    switch (j.kind) {
    case Json::Null: return "null";
    case Json::Bool: return j.boolean ? "true" : "false";
    case Json::Number: return j.text;
    case Json::String: return jsonQuote(j.text);
    case Json::Array: {
        std::string out = "[";
        for (size_t i = 0; i < j.items.size(); ++i) { if (i) out += ", "; out += dumpPython(j.items[i]); }
        return out + "]";
    }
    case Json::Object: {
        std::string out = "{";
        for (size_t i = 0; i < j.members.size(); ++i) {
            if (i) out += ", ";
            out += jsonQuote(j.members[i].first) + ": " + dumpPython(j.members[i].second);
        }
        return out + "}";
    }
    }
    return "null";
}

std::string crcHex(const std::string& bytes) {
    char buf[16];
    snprintf(buf, sizeof buf, "%08X", crc32((const unsigned char*)bytes.data(), bytes.size()));
    return buf;
}

// Boots the freshly built game hidden and silent until the runtime's own capture
// store holds the kernel pages the tested release compiled.
std::map<std::string, std::string> captureKernelPages(const Json& kernel) {
    std::set<std::string> wanted;
    for (auto& page : kernel["pages"].items) wanted.insert(page["crc32"].str());
    fs::path runDir = ctx.work / L"kernel-run";
    fs::remove_all(runDir);
    fs::create_directories(runDir / L"saves");
    fs::path store = runDir / L"overlay_captures.json";
    std::wstring env = environmentBlock({
        {L"PATH", toolPath()},
        {L"SDL_AUDIODRIVER", L"dummy"},
        {L"PSX_HEADLESS_INPUT", L"1"},
        {L"PSX_CPU_OVERCLOCK", L"300"},
        {L"PSX_OVERLAY_CAPTURES", store.wstring()},
        // Periodic capture runs only with an autocompile command; this one compiles nothing.
        {L"PSX_OVERLAY_AUTOCOMPILE_CMD", L"echo PSX_SHARD_RESULT ok=0 failed=0 skipped=0"},
    });
    std::vector<std::wstring> args{(ctx.game / L"DisruptorRecompiled.exe").wstring(), L"--no-launcher",
                                   L"--game", (ctx.root / L"game.toml").wstring(),
                                   L"--disc", (ctx.root / L"disc" / L"Disruptor.cue").wstring(),
                                   L"--memcard-dir", (runDir / L"saves").wstring(), L"--headless"};
    logLine("$ " + narrow(commandLine(args)));
    Child game;
    game.start(args, runDir, env);
    std::map<std::string, std::string> pages;
    std::set<fs::path> seen;
    std::string output;
    auto start = std::chrono::steady_clock::now();
    const int timeout = int(kernel["boot_timeout_seconds"].integer());
    while (pages.size() < wanted.size()) {
        output += game.poll();
        if (game.finished()) {
            logLine(output);
            fail("The game stopped during its first start (exit " + std::to_string(game.exitCode()) +
                 "). See the build log.");
        }
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - start).count();
        if (elapsed > timeout) {
            logLine(output);
            fail("The game did not reach its expected start-up state in time. See the build log.");
        }
        progress(76 + int(std::min<long long>(elapsed, timeout) * 10 / timeout), "Starting the game once to prepare it");
        std::vector<fs::path> files{store};
        std::error_code ec;
        if (fs::is_directory(fs::path(store) += L".d", ec))
            for (auto& e : fs::directory_iterator(fs::path(store) += L".d", ec)) files.push_back(e.path());
        for (auto& file : files) {
            if (seen.count(file) || !fs::is_regular_file(file, ec)) continue;
            try {
                Json records = Json::parse(readFile(file));
                // History snapshots are written by rename and never change; the main
                // store is replaced over time, so keep reading it.
                if (file != store) seen.insert(file);
                for (auto& rec : records.items) {
                    std::string bytes = base64Decode(rec["bytes_b64"].str());
                    std::string crc = crcHex(bytes);
                    if (wanted.count(crc)) pages[crc] = bytes;
                }
            } catch (const std::exception&) {
                // Not fully written yet; read it again on the next pass.
            }
        }
        if (pages.size() < wanted.size()) Sleep(250);
    }
    game.kill();
    output += game.poll();
    logLine(output);
    return pages;
}

void buildKernelModules() {
    const Json& kernel = ctx.recipe["kernel"];
    progress(76, "Starting the game once to prepare it");
    // Existing kernel modules would run that code natively, and the runtime only
    // captures code it has to interpret.
    fs::path cacheRoot = ctx.game / L"cache";
    fs::path cacheDir = cacheRoot / widen(kernel["cache_dir"].str());
    fs::remove_all(cacheRoot);
    auto pages = captureKernelPages(kernel);

    progress(87, "Compiling start-up kernel code");
    std::string openbios = readFile(ctx.game / L"bios" / L"openbios.bin");
    fs::path captureDir = ctx.work / L"kernel";
    fs::create_directories(captureDir);
    std::vector<fs::path> captureFiles;
    for (auto& file : kernel["captures"].items) {
        std::string out = "[";
        bool first = true;
        for (auto& rec : file["records"].items) {
            std::string bytes = pages.at(rec["page"].str());
            // The page as it was before the game patched it: the prologue words the
            // game overwrote are restored from OpenBIOS, which ships with this release.
            for (auto& r : rec["restore"].items) {
                size_t offset = size_t(r["offset"].integer()), from = size_t(r["openbios_offset"].integer()),
                       length = size_t(r["length"].integer());
                if (from + length > openbios.size() || offset + length > bytes.size()) fail("Invalid kernel recipe.");
                bytes.replace(offset, length, openbios, from, length);
            }
            if (crcHex(bytes) != rec["crc32"].str()) fail("A kernel page differs from the tested release.");
            Json fields = rec["fields"];
            for (auto& m : fields.members)
                if (m.first == "bytes_b64") { m.second.kind = Json::String; m.second.text = base64Encode(bytes); }
            out += (first ? "" : ", ") + dumpPython(fields);
            first = false;
        }
        out += "]";
        if (sha256(out) != file["sha256"].str()) fail("A kernel capture differs from the tested release.");
        fs::path path = captureDir / widen(file["file"].str());
        writeFile(path, out);
        captureFiles.push_back(path);
    }

    fs::remove_all(cacheRoot);  // the start-up run may have created an empty cache tree
    // Overlay recompiles take their BIOS address profile from <project root>/*/bios/,
    // as they do in the project repository (psxrecomp/bios/SCPH1001.toml).
    fs::copy_file(ctx.kit / L"psxrecomp" / L"bios" / L"SCPH1001.toml", ctx.work / L"psxrecomp" / L"bios" / L"SCPH1001.toml",
                  fs::copy_options::overwrite_existing);
    std::wstring env = toolEnv({
        {L"PSX_MINGW_BIN", toolchainBin().wstring()},
        {L"PYTHONHOME", L""}, {L"PYTHONPATH", L""}, {L"PYTHONNOUSERSITE", L"1"},
        {L"PYTHONUTF8", L"1"},
    });
    int step = 0;
    for (auto& capture : captureFiles) {
        std::string output = run({(ctx.kit / L"python" / L"python.exe").wstring(),
                                  (ctx.kit / L"psxrecomp" / L"tools" / L"compile_overlays.py").wstring(),
                                  L"--captures", capture.wstring(),
                                  L"--game-toml", (ctx.work / L"game.toml").wstring(),
                                  L"--recompiler", (ctx.kit / L"recompiler" / L"psxrecomp-game.exe").wstring(),
                                  L"--runtime-include", (ctx.kit / L"psxrecomp" / L"runtime" / L"include").wstring(),
                                  L"--project-root", ctx.work.wstring(),
                                  L"--out-dir", cacheRoot.wstring(),
                                  L"--compiler", L"gcc",
                                  L"--gcc", (toolchainBin() / L"gcc.exe").wstring(),
                                  L"--flavor", L"2"},
                                 ctx.work, env, "Compiling kernel code");
        if (output.find("PSX_SHARD_RESULT") == std::string::npos || output.find("failed=0") == std::string::npos)
            fail("Compiling kernel code reported a failure. See the build log.");
        progress(88 + (++step) * 3, "Compiling start-up kernel code");
    }
    for (auto& file : kernel["files"].members)
        expectHash(cacheDir / widen(file.first), file.second.str(), "Kernel code");
    for (auto& module : kernel["modules"].items)
        if (!fs::is_regular_file(cacheDir / widen(module.str())))
            fail("A kernel module was not produced: " + module.str());
    // The translated sources were only needed for the check above.
    for (auto& e : fs::directory_iterator(cacheDir))
        if (e.path().extension() == L".c") fs::remove(e.path());
}

// ------------------------------------------------------------------ 8. finish
void writeStamp() {
    std::string modules;
    for (auto& m : ctx.recipe["kernel"]["modules"].items) modules += (modules.empty() ? "" : ", ") + jsonQuote(m.str());
    SYSTEMTIME t{};
    GetSystemTime(&t);
    char when[40];
    snprintf(when, sizeof when, "%04d-%02d-%02dT%02d:%02d:%02dZ", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond);
    writeFile(ctx.game / L"build-stamp.json",
              "{\n  \"version\": " + jsonQuote(ctx.recipe["version"].str()) +
              ",\n  \"exe_normalized_sha256\": " + jsonQuote(ctx.recipe["link"]["normalized_sha256"].str()) +
              ",\n  \"kernel_modules\": [" + modules + "],\n  \"built_utc\": " + jsonQuote(when) + "\n}\n");
}

void build() {
    ctx.recipe = Json::parse(readFile(ctx.kit / L"recipe.json"));
    logLine("Disruptor Recompiled builder " + ctx.recipe["version"].str());
    logLine("installation: " + u8path(ctx.root));
    // A stale stamp must never vouch for a half-built game.
    std::error_code ec;
    fs::remove(ctx.game / L"build-stamp.json", ec);
    fs::remove_all(ctx.work, ec);
    fs::create_directories(ctx.work);
    // The recompiler resolves game.toml's relative paths against the nearest folder
    // (up to 8 levels up) holding .gitignore, .git or CMakeLists.txt; anchor it here.
    writeFile(ctx.work / L".gitignore", "*\n");
    fs::create_directories(ctx.work / L"tmp");
    fs::create_directories(ctx.game);
    ctx.kit = toolSafe(ctx.kit);
    ctx.work = toolSafe(ctx.work);
    ctx.game = toolSafe(ctx.game);
    progress(0, "Preparing");
    verifyDisc();
    extractExecutable();
    writeSeeds();
    recompile();
    compileGame();
    linkGame();
    buildKernelModules();
    writeStamp();
    if (!ctx.keepWork) fs::remove_all(ctx.work, ec);
    progress(100, "Disruptor is ready");
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    SetConsoleOutputCP(CP_UTF8);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    try {
        ctx.root = executablePath().parent_path();
        for (int i = 1; i < argc; ++i) {
            std::wstring a = argv[i];
            auto value = [&]() -> std::wstring {
                if (i + 1 >= argc) throw BuildError("Missing value for " + narrow(a));
                return argv[++i];
            };
            if (a == L"--root") ctx.root = fs::absolute(value());
            else if (a == L"--disc") ctx.disc = fs::absolute(value());
            else if (a == L"--log") ctx.logPath = fs::absolute(value());
            else if (a == L"--jobs") ctx.jobs = std::stoi(value());
            else if (a == L"--keep-work") ctx.keepWork = true;
            else throw BuildError("Unknown option " + narrow(a));
        }
        ctx.kit = ctx.root / L"kit";
        ctx.game = ctx.root / L"game";
        ctx.work = ctx.root / L"work";
        if (ctx.disc.empty()) ctx.disc = ctx.root / L"disc" / L"Disruptor.bin";
        if (ctx.logPath.empty()) ctx.logPath = userDataPath() / L"logs" / L"build-last.log";
        fs::create_directories(ctx.logPath.parent_path());
        ctx.log.open(ctx.logPath, std::ios::trunc);
        auto started = std::chrono::steady_clock::now();
        build();
        auto seconds = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - started).count();
        logLine("build finished in " + std::to_string(seconds) + " s");
        return 0;
    } catch (const std::exception& e) {
        logLine(std::string("ERROR ") + e.what());
        printf("ERROR %s\n", e.what());
        fflush(stdout);
        return 1;
    }
}
