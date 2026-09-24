// Native, dependency-free player frontend: builds the game on first start (via
// DisruptorBuilder.exe), offers every player setting, and starts the game.
#include "common.hpp"
#include <shellapi.h>
#include <dwmapi.h>
#include <windowsx.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <mutex>
#include <optional>
#include <thread>
#include "release_config.h"

namespace {

// ================================================================ look
constexpr COLORREF BG = RGB(12, 17, 24), PANEL = RGB(22, 31, 42), PANEL_HI = RGB(31, 45, 60);
constexpr COLORREF INK = RGB(236, 244, 247), MUTED = RGB(152, 173, 185), DIM = RGB(92, 112, 124);
constexpr COLORREF CYAN = RGB(91, 232, 218), CYAN_DOWN = RGB(60, 190, 181), LINE = RGB(39, 57, 70);
constexpr COLORREF WARN = RGB(255, 184, 137);
constexpr int WIDTH = 960, HEIGHT = 640;  // logical (96 DPI) client size
constexpr UINT MSG_VERIFIED = WM_APP + 1, MSG_VERIFY_PROGRESS = WM_APP + 2, MSG_BUILD = WM_APP + 3,
               MSG_BUILD_DONE = WM_APP + 4;

HWND window = nullptr;
UINT dpi = 96;
HFONT fontTitle, fontHuge, fontHeading, fontBody, fontSmall, fontTiny;

fs::path root, gameDir, userData;

// ================================================================ settings
struct Option { std::wstring label; std::string value; };
struct Setting {
    std::string key;
    int category;
    std::wstring label, help;
    std::vector<Option> options;
    int def = 0, value = 0;
    bool action = false;  // a button row rather than a value
    bool toggle() const { return !action && options.size() == 2 && options[0].label == L"Off" && options[1].label == L"On"; }
    const std::string& v() const { return options[size_t(value)].value; }
};
const wchar_t* CATEGORIES[] = {L"DISPLAY", L"GRAPHICS", L"CONTROLS", L"AUDIO", L"ADVANCED"};
enum { DISPLAY, GRAPHICS, CONTROLS, AUDIO, ADVANCED };
std::vector<Setting> settings;

std::vector<Option> offOn() { return {{L"Off", "0"}, {L"On", "1"}}; }
std::vector<Option> range(double lo, double hi, double step, int decimals, const wchar_t* suffix, double scale = 1) {
    std::vector<Option> out;
    for (double x = lo; x <= hi + step / 2; x += step) {
        wchar_t label[32];
        char value[32];
        swprintf(label, 32, L"%.*f%ls", decimals, x * scale, suffix);
        snprintf(value, 32, "%.*f", decimals, x);
        out.push_back({label, value});
    }
    return out;
}
void add(std::string key, int cat, std::wstring label, std::wstring help, std::vector<Option> options, int def) {
    settings.push_back({std::move(key), cat, std::move(label), std::move(help), std::move(options), def, def});
}
void defineSettings() {
    add("window_mode", DISPLAY, L"Window mode", L"Borderless fullscreen uses your desktop resolution. Alt+Enter switches while playing.",
        {{L"Borderless fullscreen", "1"}, {L"Windowed", "0"}, {L"Exclusive fullscreen", "2"}}, 0);
    add("window_width", DISPLAY, L"Window size", L"Width of the game window when it is not fullscreen.",
        {{L"Automatic", ""}, {L"1280 wide", "1280"}, {L"1600 wide", "1600"}, {L"1920 wide", "1920"}, {L"2560 wide", "2560"}}, 0);
    add("widescreen", DISPLAY, L"Widescreen 16:9", L"Widens the 3D view with real extra scenery. Menus and movies keep their shape. Off plays in the original 4:3.",
        offOn(), 1);
    add("vsync", DISPLAY, L"Vertical sync", L"Off gives the lowest input lag and suits G-SYNC / FreeSync screens. Turn it on if you see tearing.",
        {{L"Off (lowest latency)", "immediate"}, {L"On", "on"}, {L"Adaptive", "adaptive"}}, 0);
    add("low_latency", DISPLAY, L"Low-latency input", L"Reads your controls as late as possible before each frame.", offOn(), 1);

    add("resolution", GRAPHICS, L"Internal resolution", L"Draws the 3D world at a multiple of the original 320 x 240.",
        {{L"1x (original)", "1"}, {L"2x", "2"}, {L"3x", "3"}, {L"4x", "4"}}, 3);
    add("filter", GRAPHICS, L"Texture filtering", L"Smart smooths the world while keeping sprites, weapons and text crisp.",
        {{L"Smart", "smart"}, {L"Smooth everywhere", "bilinear"}, {L"Original pixels", "nearest"}}, 0);
    add("tile_blend", GRAPHICS, L"Terrain seam blending", L"Blends colour and light across the edges of terrain tiles. Needs Smart filtering.", offOn(), 1);
    add("crack_fill", GRAPHICS, L"Close polygon gaps", L"Hides the hairline gaps between polygons that show at high resolution.", offOn(), 1);
    add("geometry", GRAPHICS, L"Geometry correction", L"Keeps polygons steady instead of wobbling (PGXP).", offOn(), 1);
    add("perspective", GRAPHICS, L"Perspective-correct textures", L"Removes the warping of textures on walls and floors.", offOn(), 1);
    add("fmv_filter", GRAPHICS, L"Movie smoothing", L"How the full-motion videos are scaled up.",
        {{L"Bicubic", "bicubic"}, {L"Bilinear", "bilinear"}, {L"Sharp", "sharp"}, {L"Off", "nearest"}}, 0);
    add("fmv_fill", GRAPHICS, L"Enlarge movies", L"Shows the movies' whole picture as large as your screen allows.", offOn(), 1);
    add("screen", GRAPHICS, L"Screen style", L"Colour response of a television.",
        {{L"Clean", "raw"}, {L"CRT", "crt"}, {L"Composite", "composite"}, {L"Trinitron", "trinitron"}}, 0);
    add("scanlines", GRAPHICS, L"Scanlines", L"TV scanlines. F6 switches them while playing.",
        {{L"Off", "0"}, {L"Light", "0.25"}, {L"Medium", "0.5"}, {L"Strong", "0.75"}}, 0);
    add("smooth_scaling", GRAPHICS, L"Smooth screen scaling", L"Softens the final picture when it is scaled to your screen.", offOn(), 0);

    add("mouselook", CONTROLS, L"Mouse look", L"Turn with the mouse. Off uses the original turning on keys or controller.", offOn(), 1);
    add("mouse_sens", CONTROLS, L"Mouse sensitivity", L"How far the view turns per mouse movement.", range(0.05, 1.0, 0.05, 2, L""), 5);
    add("smooth_yaw", CONTROLS, L"Smooth turning", L"Spreads each mouse movement evenly over the frames it spans.", offOn(), 1);
    add("wheel_select", CONTROLS, L"Mouse wheel selects weapons", L"Scroll to change weapon. Hold R and scroll for psionic powers.", offOn(), 1);
    add("pad", CONTROLS, L"Controller", L"Automatic uses a connected gamepad together with keyboard and mouse.",
        {{L"Automatic", "auto"}, {L"Keyboard and mouse only", "keyboard"}}, 0);
    add("deadzone", CONTROLS, L"Stick deadzone", L"How far a stick must move before it counts.", range(0, 0.30, 0.05, 2, L"%", 100), 2);
    for (auto& o : settings.back().options) o.label = std::to_wstring(int(std::lround(std::stod(o.value) * 100))) + L"%";
    settings.push_back({"bindings", CONTROLS, L"Keys and mouse buttons", L"See and change which key or button does what.", {{L"Open", ""}}, 0, 0, true});

    add("frequency", AUDIO, L"Output sample rate", L"Keypad + and - change the volume while playing.",
        {{L"44.1 kHz", "44100"}, {L"48 kHz", "48000"}}, 0);
    add("spu_hq", AUDIO, L"High-quality sound processing", L"More precise mixing of the console's sound chip.", offOn(), 0);

    add("overclock", ADVANCED, L"Console CPU speed", L"300% keeps busy scenes at 60 fps. 100% is the original console. Game speed is not affected.",
        range(100, 400, 25, 0, L"%"), 8);
    add("interp", ADVANCED, L"Frame interpolation (experimental)", L"Adds in-between frames up to your monitor's refresh rate.",
        {{L"Off", ""}, {L"On", "0"}}, 0);
    add("ff_speed", ADVANCED, L"Fast-forward speed (hold Tab)", L"F9 keeps fast-forward on until you press it again.",
        {{L"2x", "2"}, {L"3x", "3"}, {L"4x", "4"}, {L"8x", "8"}, {L"Unlimited", "max"}}, 2);
    add("fps", ADVANCED, L"Show FPS counter", L"F10 shows or hides it while playing.", offOn(), 0);
    add("fast_loading", ADVANCED, L"Faster loading (experimental)", L"Shortens disc loading. Not fully tested with this game.", offOn(), 0);
    settings.push_back({"rebuild", ADVANCED, L"Rebuild the game", L"Builds the game again from your disc image, for example after a failed update.", {{L"Rebuild", ""}}, 0, 0, true});
}
Setting& S(const std::string& key) {
    for (auto& s : settings) if (s.key == key) return s;
    throw std::runtime_error("unknown setting " + key);
}

// ================================================================ config files
std::string trimmed(std::string s) {
    size_t a = s.find_first_not_of(" \t\r"), b = s.find_last_not_of(" \t\r");
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}
// Line-preserving editor for the INI/TOML files the runtime reads: comments and
// unknown keys survive, known keys are replaced in place or added to their section.
struct LineDoc {
    std::vector<std::string> lines;
    void load(const fs::path& path) {
        lines.clear();
        std::error_code ec;
        if (!fs::is_regular_file(path, ec)) return;
        std::string text = readFile(path), line;
        std::istringstream in(text);
        while (std::getline(in, line)) { if (!line.empty() && line.back() == '\r') line.pop_back(); lines.push_back(line); }
    }
    void save(const fs::path& path) const {
        std::string out;
        for (auto& l : lines) out += l + "\n";
        writeFile(path, out);
    }
    static bool isHeader(const std::string& t) { return !t.empty() && t[0] == '['; }
    // Index range [begin, end) of a section's body; begin == npos if absent.
    std::pair<size_t, size_t> section(const std::string& name) const {
        size_t begin = std::string::npos;
        for (size_t i = 0; i < lines.size(); ++i) {
            std::string t = trimmed(lines[i]);
            if (begin == std::string::npos) { if (t == "[" + name + "]") begin = i + 1; }
            else if (isHeader(t)) return {begin, i};
        }
        return {begin, lines.size()};
    }
    static bool keyLine(const std::string& line, const std::string& key) {
        std::string t = trimmed(line);
        if (t.rfind(key, 0) != 0) return false;
        std::string rest = trimmed(t.substr(key.size()));
        return !rest.empty() && rest[0] == '=';
    }
    std::optional<std::string> get(const std::string& sec, const std::string& key) const {
        auto [b, e] = section(sec);
        if (b == std::string::npos) return std::nullopt;
        for (size_t i = b; i < e; ++i)
            if (keyLine(lines[i], key)) {
                std::string v = trimmed(lines[i].substr(lines[i].find('=') + 1));
                if (v.size() >= 2 && v.front() == '"' && v.back() == '"') v = v.substr(1, v.size() - 2);
                return v;
            }
        return std::nullopt;
    }
    void set(const std::string& sec, const std::string& key, const std::string& value) {
        auto [b, e] = section(sec);
        if (b == std::string::npos) {
            if (!lines.empty() && !trimmed(lines.back()).empty()) lines.push_back("");
            lines.push_back("[" + sec + "]");
            lines.push_back(key + " = " + value);
            return;
        }
        for (size_t i = b; i < e; ++i)
            if (keyLine(lines[i], key)) { lines[i] = key + " = " + value; return; }
        size_t at = e;
        while (at > b && trimmed(lines[at - 1]).empty()) --at;  // keep the blank line before the next section
        lines.insert(lines.begin() + long(at), key + " = " + value);
    }
    void erase(const std::string& sec, const std::string& key) {
        auto [b, e] = section(sec);
        if (b == std::string::npos) return;
        for (size_t i = b; i < e; ++i)
            if (keyLine(lines[i], key)) { lines.erase(lines.begin() + long(i)); return; }
    }
};
std::string quoted(const std::string& s) { return "\"" + s + "\""; }
std::string boolText(bool b) { return b ? "true" : "false"; }

fs::path launcherIni() { return gameDir / L"launcher.ini"; }

void loadSettings() {
    LineDoc doc;
    doc.load(launcherIni());
    for (auto& s : settings) {
        if (s.action) continue;
        if (auto v = doc.get("settings", s.key))
            for (size_t i = 0; i < s.options.size(); ++i)
                if (s.options[i].value == *v) s.value = int(i);
    }
}

// The runtime reads settings.toml, mods/state.toml and environment variables. This
// build of the runtime never writes settings.toml, so the launcher owns it.
void writeRuntimeSettings() {
    LineDoc ini;
    ini.load(launcherIni());
    if (ini.lines.empty()) ini.lines = {"# Disruptor Recompiled launcher settings. Change them in the launcher."};
    for (auto& s : settings)
        if (!s.action) ini.set("settings", s.key, s.v());
    ini.save(launcherIni());

    LineDoc toml;
    toml.load(gameDir / L"settings.toml");
    toml.set("video", "fullscreen", S("window_mode").v());
    if (S("window_width").v().empty()) toml.erase("video", "window_width");
    else toml.set("video", "window_width", S("window_width").v());
    toml.set("video", "vsync", quoted(S("vsync").v()));
    toml.set("video", "low_latency_input", boolText(S("low_latency").value));
    toml.set("video", "supersampling", S("resolution").v());
    toml.set("video", "texture_filtering", quoted(S("filter").v() == "bilinear" ? "bilinear" : "nearest"));
    toml.set("video", "antialiasing", boolText(S("smooth_scaling").value));
    toml.set("video", "fmv_filter", quoted(S("fmv_filter").v()));
    toml.set("video", "geometry_correction", boolText(S("geometry").value));
    toml.set("video", "perspective_texturing", boolText(S("perspective").value));
    toml.set("video", "crt_filter", quoted(S("screen").v()));
    toml.set("video", "scanlines", boolText(S("scanlines").value != 0));
    if (S("scanlines").value) toml.set("video", "scanline_strength", S("scanlines").v());
    toml.set("audio", "frequency", S("frequency").v());
    toml.set("audio", "spu_hq", boolText(S("spu_hq").value));
    toml.set("controller", "p1_device", quoted(S("pad").v()));
    toml.set("controller", "p1_deadzone", std::to_string(int(std::lround(std::stod(S("deadzone").v()) * 32767))));
    toml.save(gameDir / L"settings.toml");

    // Mod features live in mods/state.toml, which the runtime rewrites on each start.
    // Only the "enabled" lines of the features below are touched.
    struct Feature { const char* package; const char* id; bool on; };
    Feature features[] = {
        {"disruptor.presentation.widescreen", "widescreen", S("widescreen").value != 0},
        {"disruptor.presentation.widescreen", "mouselook", S("mouselook").value != 0},
        {"disruptor.presentation.widescreen", "wheel_select", S("wheel_select").value != 0},
        {"psx.enhancement.fast-loading", "fast-loading", S("fast_loading").value != 0},
    };
    fs::path statePath = gameDir / L"mods" / L"state.toml";
    LineDoc state;
    state.load(statePath);
    if (state.lines.empty()) state.lines = {"format_version = 2"};
    for (auto& f : features) {
        bool found = false;
        for (size_t i = 0; i < state.lines.size() && !found; ++i) {
            if (trimmed(state.lines[i]) != "[[feature]]") continue;
            size_t end = i + 1;
            while (end < state.lines.size() && !LineDoc::isHeader(trimmed(state.lines[end]))) ++end;
            bool pkg = false, id = false;
            size_t enabledLine = std::string::npos;
            for (size_t j = i + 1; j < end; ++j) {
                std::string t = trimmed(state.lines[j]);
                if (LineDoc::keyLine(t, "package_id")) pkg = t.find(quoted(f.package)) != std::string::npos;
                if (LineDoc::keyLine(t, "id")) id = t.find(quoted(f.id)) != std::string::npos;
                if (LineDoc::keyLine(t, "enabled")) enabledLine = j;
            }
            if (!pkg || !id) continue;
            found = true;
            if (enabledLine != std::string::npos) state.lines[enabledLine] = "enabled = " + boolText(f.on);
            else state.lines.insert(state.lines.begin() + long(end), "enabled = " + boolText(f.on));
        }
        if (!found) {
            state.lines.push_back("");
            state.lines.push_back("[[feature]]");
            state.lines.push_back("package_id = " + quoted(f.package));
            state.lines.push_back("id = " + quoted(f.id));
            state.lines.push_back("enabled = " + boolText(f.on));
        }
    }
    fs::create_directories(statePath.parent_path());
    state.save(statePath);
}

std::vector<std::pair<std::wstring, std::wstring>> gameEnvironment() {
    auto w = [](const std::string& s) { return widen(s); };
    bool smart = S("filter").v() == "smart";
    return {
        {L"PSX_OVERLAY_AUTOCOMPILE_OFF", L"1"},  // compiling during play would stutter
        {L"PSX_CPU_OVERCLOCK", w(S("overclock").v())},
        {L"PSX_GL_SMART_FILTER", smart ? L"1" : L"0"},
        {L"PSX_GL_TILE_BLEND", smart && S("tile_blend").value ? L"1.0" : L""},
        {L"PSX_GL_CRACK_FILL", S("crack_fill").value ? L"0.45" : L""},
        {L"PSX_GL_FMV_FILTER", w(S("fmv_filter").v())},
        {L"PSX_GL_FMV_CONTENT", S("fmv_fill").value ? L"320x180" : L""},
        {L"DISRUPTOR_MOUSE_SENS", w(S("mouse_sens").v())},
        {L"DISRUPTOR_SMOOTH_YAW", S("smooth_yaw").value ? L"" : L"0"},
        {L"DISRUPTOR_INTERP_FPS", w(S("interp").v())},
        {L"PSX_FAST_FORWARD_SPEED", w(S("ff_speed").v())},
        {L"PSX_FPS_TELEMETRY", S("fps").value ? L"1" : L""},
    };
}

// ================================================================ key bindings
struct Action { const char* key; const wchar_t* label; const wchar_t* button; };
const Action ACTIONS[] = {
    {"up", L"Move forward", L"Up"},       {"down", L"Move back", L"Down"},
    {"left", L"Turn left", L"Left"},      {"right", L"Turn right", L"Right"},
    {"l2", L"Strafe left", L"L2"},        {"r2", L"Strafe right", L"R2"},
    {"cross", L"Fire / confirm", L"Cross"},
    {"square", L"Psionic power", L"Square"},
    {"circle", L"Circle", L"Circle"},     {"triangle", L"Triangle", L"Triangle"},
    {"l1", L"Weapon list (hold)", L"L1"}, {"r1", L"Psionic list (hold)", L"R1"},
    {"start", L"Pause", L"Start"},        {"select", L"Select", L"Select"},
};
constexpr int ACTION_COUNT = int(sizeof(ACTIONS) / sizeof(ACTIONS[0]));
std::string bindings[ACTION_COUNT][2];

void loadBindings() {
    LineDoc doc;
    doc.load(gameDir / L"keybinds.ini");
    for (int i = 0; i < ACTION_COUNT; ++i) {
        bindings[i][0] = bindings[i][1] = "None";
        if (auto v = doc.get("player1", ACTIONS[i].key)) {
            size_t comma = v->find(',');
            bindings[i][0] = trimmed(v->substr(0, comma));
            if (comma != std::string::npos) bindings[i][1] = trimmed(v->substr(comma + 1));
        }
    }
}
void saveBindings() {
    LineDoc doc;
    doc.load(gameDir / L"keybinds.ini");
    for (int i = 0; i < ACTION_COUNT; ++i) {
        std::string v = bindings[i][0];
        if (bindings[i][1] != "None") v += ", " + bindings[i][1];
        doc.set("player1", ACTIONS[i].key, v);
    }
    doc.save(gameDir / L"keybinds.ini");
}
void restoreDefaultBindings() {
    // The installed default layout is kept in kit/defaults.
    std::error_code ec;
    fs::copy_file(root / L"kit" / L"defaults" / L"keybinds.ini", gameDir / L"keybinds.ini", fs::copy_options::overwrite_existing, ec);
    loadBindings();
}
std::wstring bindingLabel(const std::string& name) {
    static const std::pair<const char*, const wchar_t*> names[] = {
        {"Mouse1", L"Left click"}, {"Mouse2", L"Middle click"}, {"Mouse3", L"Right click"},
        {"Mouse4", L"Mouse button 4"}, {"Mouse5", L"Mouse button 5"}, {"MouseWheelUp", L"Wheel up"},
        {"MouseWheelDown", L"Wheel down"}, {"None", L"—"}};
    for (auto& n : names) if (_stricmp(n.first, name.c_str()) == 0) return n.second;
    return widen(name);
}
// SDL names by PC scan code (key position), which is what the runtime binds.
std::string keyName(UINT scan, bool extended) {
    static const char* main[0x59] = {
        nullptr, "Escape", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace", "Tab",
        "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "Return", "Left Ctrl", "A", "S",
        "D", "F", "G", "H", "J", "K", "L", ";", "'", "`", "Left Shift", "\\", "Z", "X", "C", "V",
        "B", "N", "M", ",", ".", "/", "Right Shift", "Keypad *", "Left Alt", "Space", "CapsLock", "F1", "F2", "F3",
        "F4", "F5", "F6", "F7", "F8", "F9", "F10", nullptr, nullptr, "Keypad 7", "Keypad 8", "Keypad 9", "Keypad -", "Keypad 4", "Keypad 5", "Keypad 6",
        "Keypad +", "Keypad 1", "Keypad 2", "Keypad 3", "Keypad 0", "Keypad .", nullptr, nullptr, nullptr, "F11", "F12"};
    if (extended) {
        switch (scan) {
        case 0x1C: return "Keypad Enter";
        case 0x1D: return "Right Ctrl";
        case 0x35: return "Keypad /";
        case 0x38: return "Right Alt";
        case 0x47: return "Home";
        case 0x48: return "Up";
        case 0x49: return "PageUp";
        case 0x4B: return "Left";
        case 0x4D: return "Right";
        case 0x4F: return "End";
        case 0x50: return "Down";
        case 0x51: return "PageDown";
        case 0x52: return "Insert";
        case 0x53: return "Delete";
        default: return "";
        }
    }
    return scan < 0x59 && main[scan] ? main[scan] : "";
}

// ================================================================ state
enum Page { HOME, SETTINGS, BINDINGS };
Page page = HOME;
int category = DISPLAY, row = 0;          // settings selection
int bindRow = 0, bindCol = 0;             // bindings selection
bool capturing = false;                   // waiting for a key for bindings[bindRow][bindCol]
bool captureArmed = false;                // ignore the click that started capturing
bool swallowUp = false;                   // the button release after binding a left click

enum Status { CHECKING, READY, NEEDS_BUILD, BUILDING, BUILD_FAILED, BAD_DISC, RUNNING };
Status status = CHECKING;
int percent = 0;
std::wstring buildText, buildError;
std::atomic<bool> cancelVerify{false};
std::thread verifier, buildThread;
std::unique_ptr<Child> builder;
HANDLE gameProcess = nullptr;
bool closeAfterGame = false;

bool gameBuilt() {
    std::error_code ec;
    if (!fs::is_regular_file(gameDir / L"DisruptorRecompiled.exe", ec)) return false;
    try {
        Json stamp = Json::parse(readFile(gameDir / L"build-stamp.json"));
        return stamp["version"].str() == RELEASE_VERSION;
    } catch (...) { return false; }
}

bool verifyDisc(const fs::path& path, HWND notify = nullptr) {
    try {
        std::error_code ec;
        if (!fs::is_regular_file(path, ec) || fs::file_size(path, ec) != DISC_SIZE) return false;
        int last = -1;
        std::string hash = sha256File(path, [&](uint64_t done, uint64_t total) {
            int pct = int(done * 100 / (total ? total : 1));
            if (notify && pct != last) PostMessageW(notify, MSG_VERIFY_PROGRESS, WPARAM(pct), 0);
            last = pct;
            return !cancelVerify.load();
        });
        return hash == DISC_SHA256;
    } catch (...) { return false; }
}

void refresh() { if (window) InvalidateRect(window, nullptr, FALSE); }

// ---------------------------------------------------------------- build
void startBuild() {
    if (status == BUILDING || status == RUNNING) return;
    if (buildThread.joinable()) buildThread.join();
    status = BUILDING;
    percent = 0;
    buildText = L"Preparing";
    buildError.clear();
    page = HOME;
    refresh();
    try {
        builder = std::make_unique<Child>();
        builder->start({(root / L"DisruptorBuilder.exe").wstring()}, root, environmentBlock({}, false), true,
                       BELOW_NORMAL_PRIORITY_CLASS);
    } catch (const std::exception& e) {
        builder.reset();
        status = BUILD_FAILED;
        buildError = widen(e.what());
        return;
    }
    buildThread = std::thread([] {
        std::string pending;
        Child* child = builder.get();
        auto consume = [&]() {
            pending += child->poll();
            size_t nl;
            while ((nl = pending.find('\n')) != std::string::npos) {
                std::string line = trimmed(pending.substr(0, nl));
                pending.erase(0, nl + 1);
                if (line.rfind("PROGRESS ", 0) == 0) {
                    size_t sp = line.find(' ', 9);
                    auto* text = new std::wstring(widen(sp == std::string::npos ? "" : line.substr(sp + 1)));
                    PostMessageW(window, MSG_BUILD, WPARAM(std::atoi(line.c_str() + 9)), LPARAM(text));
                } else if (line.rfind("ERROR ", 0) == 0) {
                    PostMessageW(window, MSG_BUILD, WPARAM(-1), LPARAM(new std::wstring(widen(line.substr(6)))));
                }
            }
        };
        while (!child->finished()) { consume(); WaitForSingleObject(child->handle(), 100); }
        consume();
        PostMessageW(window, MSG_BUILD_DONE, child->exitCode(), 0);
    });
}

// ---------------------------------------------------------------- game
std::wstring quote(const fs::path& p) { return L"\"" + p.wstring() + L"\""; }
bool launchGame(bool headless = false) {
    fs::create_directories(userData / L"saves");
    fs::create_directories(userData / L"logs");
    writeRuntimeSettings();
    fs::path exe = gameDir / L"DisruptorRecompiled.exe";
    std::wstring cmd = quote(exe) + L" --no-launcher --game " + quote(root / L"game.toml") + L" --disc " +
                       quote(root / L"disc" / L"Disruptor.cue") + L" --memcard-dir " + quote(userData / L"saves");
    if (headless) cmd += L" --headless";
    auto vars = gameEnvironment();
    if (headless) vars.push_back({L"SDL_AUDIODRIVER", L"dummy"});
    std::wstring env = environmentBlock(vars);
    SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
    HANDLE log = CreateFileW((userData / L"logs" / L"game-last.log").c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    HANDLE input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr);
    if (log == INVALID_HANDLE_VALUE || input == INVALID_HANDLE_VALUE) {
        if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
        if (input != INVALID_HANDLE_VALUE) CloseHandle(input);
        return false;
    }
    STARTUPINFOW si{sizeof(si)};
    PROCESS_INFORMATION pi{};
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = log;
    si.hStdError = log;
    si.hStdInput = input;
    // One busy thread must finish every frame in 16.7 ms; keep it ahead of background work.
    bool ok = CreateProcessW(exe.c_str(), cmd.data(), nullptr, nullptr, TRUE,
                             CREATE_NO_WINDOW | HIGH_PRIORITY_CLASS | CREATE_UNICODE_ENVIRONMENT, (LPVOID)env.c_str(),
                             root.c_str(), &si, &pi);
    CloseHandle(log);
    CloseHandle(input);
    if (ok) { gameProcess = pi.hProcess; CloseHandle(pi.hThread); }
    return ok;
}
void openFolder(const wchar_t* name) {
    auto path = userData / name;
    fs::create_directories(path);
    ShellExecuteW(window, L"open", path.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
}

// ================================================================ drawing
struct Hit { RECT r; int id; int a; int b; };
std::vector<Hit> hits;
int hot = -1, hotA = -1, hotB = -1, pressed = -1;
enum HitId { H_PLAY = 1, H_SETTINGS, H_CONTROLS, H_SAVES, H_LOGS, H_TAB_HOME, H_TAB_SETTINGS, H_TAB_CONTROLS,
             H_CATEGORY, H_ROW, H_DEC, H_INC, H_BACK, H_DEFAULTS, H_BIND, H_BIND_DEFAULTS };

void hit(int x, int y, int w, int h, int id, int a = 0, int b = 0) { hits.push_back({{x, y, x + w, y + h}, id, a, b}); }
bool isHot(int id, int a = 0, int b = 0) { return hot == id && hotA == a && hotB == b; }

void fill(HDC dc, int x, int y, int w, int h, COLORREF c) {
    RECT r{x, y, x + w, y + h};
    HBRUSH b = CreateSolidBrush(c);
    FillRect(dc, &r, b);
    DeleteObject(b);
}
void text(HDC dc, const std::wstring& s, int x, int y, int w, int h, HFONT f, COLORREF c,
          UINT flags = DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS) {
    auto old = SelectObject(dc, f);
    SetTextColor(dc, c);
    RECT r{x, y, x + w, y + h};
    DrawTextW(dc, s.c_str(), -1, &r, flags | DT_NOPREFIX);
    SelectObject(dc, old);
}
void line(HDC dc, int x1, int y1, int x2, int y2, COLORREF c, int width = 1) {
    HPEN pen = CreatePen(PS_SOLID, width, c);
    auto old = SelectObject(dc, pen);
    MoveToEx(dc, x1, y1, nullptr);
    LineTo(dc, x2, y2);
    SelectObject(dc, old);
    DeleteObject(pen);
}
void button(HDC dc, int x, int y, int w, int h, const std::wstring& label, int id, bool primary, bool enabled = true,
            int a = 0) {
    bool over = enabled && isHot(id, a), down = over && pressed == id;
    COLORREF bg = primary ? (enabled ? (down ? CYAN_DOWN : CYAN) : PANEL) : (down ? PANEL_HI : over ? PANEL_HI : PANEL);
    fill(dc, x, y, w, h, bg);
    if (!primary && over) fill(dc, x, y + h - 2, w, 2, CYAN);
    COLORREF fg = primary && enabled ? BG : (enabled ? INK : DIM);
    text(dc, label, x + 10, y, w - 20, h, primary ? fontHeading : fontBody, fg, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    if (enabled) hit(x, y, w, h, id, a);
}
// Original vector motif: nested portals.
void portals(HDC dc, int ox, int oy, double scale) {
    for (int i = 0; i < 6; ++i) {
        int x = ox + int(i * 12 * scale), y = oy + int(i * 13 * scale), w = int((184 - i * 24) * scale), h = int((155 - i * 23) * scale);
        int k = int(22 * scale);
        COLORREF c = i == 5 ? CYAN : RGB(26 + i * 7, 60 + i * 17, 66 + i * 17);
        line(dc, x, y, x + w - k, y, c, 2); line(dc, x + w - k, y, x + w, y + k, c, 2);
        line(dc, x + w, y + k, x + w, y + h, c, 2); line(dc, x + w, y + h, x, y + h, c, 2); line(dc, x, y + h, x, y, c, 2);
    }
}
void tabs(HDC dc) {
    const wchar_t* names[] = {L"HOME", L"SETTINGS", L"CONTROLS"};
    int ids[] = {H_TAB_HOME, H_TAB_SETTINGS, H_TAB_CONTROLS};
    Page pages[] = {HOME, SETTINGS, BINDINGS};
    int x = 600;
    for (int i = 0; i < 3; ++i) {
        int w = i == 0 ? 80 : 110;
        bool active = page == pages[i];
        text(dc, names[i], x, 26, w, 30, fontSmall, active ? INK : isHot(ids[i]) ? INK : MUTED, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        if (active) fill(dc, x + 16, 58, w - 32, 2, CYAN);
        hit(x, 22, w, 40, ids[i]);
        x += w + 4;
    }
}
void header(HDC dc, const std::wstring& title, const std::wstring& subtitle) {
    fill(dc, 40, 36, 32, 3, CYAN);
    text(dc, title, 38, 50, 500, 40, fontHuge, INK);
    text(dc, subtitle, 40, 90, 540, 24, fontSmall, MUTED);
    tabs(dc);
}

std::wstring statusText() {
    switch (status) {
    case CHECKING: return L"Checking your disc image...  " + std::to_wstring(percent) + L"%";
    case READY: return L"Disc verified  /  Built on this PC  /  Ready to play";
    case NEEDS_BUILD: return L"Disc verified. The game has to be built on this PC once (about a minute).";
    case BUILDING: return buildText + L"...  " + std::to_wstring(percent) + L"%";
    case BUILD_FAILED: return L"The build did not finish: " + buildError;
    case BAD_DISC: return L"Disc image missing or unsupported. Run Setup again and select your Disruptor USA image.";
    case RUNNING: return L"Game running. Your saves are kept in your Windows profile.";
    }
    return L"";
}

void paintHome(HDC dc) {
    fill(dc, 40, 36, 32, 3, CYAN);
    text(dc, L"THE PLAYSTATION ORIGINAL. RECOMPILED FOR WINDOWS.", 84, 25, 500, 24, fontSmall, MUTED);
    tabs(dc);
    text(dc, L"DISRUPTOR", 36, 82, 600, 80, fontTitle, INK);
    text(dc, L"R E C O M P I L E D", 42, 160, 500, 32, fontHeading, CYAN);
    text(dc, L"A familiar world. A sharper view.", 42, 208, 530, 30, fontBody, MUTED);
    portals(dc, 690, 92, 1.0);
    fill(dc, 40, 272, 880, 74, PANEL);
    const wchar_t* feature[] = {L"60 FPS", L"WIDESCREEN", L"MOUSE + KEYBOARD", L"BUILT ON YOUR PC"};
    const wchar_t* detail[] = {L"Original game speed", L"True 16:9 view", L"Controllers supported", L"From your own disc"};
    for (int i = 0; i < 4; ++i) {
        int x = 60 + i * 220;
        text(dc, feature[i], x, 283, 205, 25, fontBody, INK);
        text(dc, detail[i], x, 310, 205, 23, fontSmall, MUTED);
        if (i < 3) line(dc, x + 205, 290, x + 205, 330, LINE);
    }
    bool warn = status == BAD_DISC || status == BUILD_FAILED;
    fill(dc, 40, 381, 6, 6, warn ? RGB(255, 164, 108) : CYAN);
    text(dc, statusText(), 58, 368, 862, 30, fontBody, warn ? WARN : MUTED);
    if (status == CHECKING || status == BUILDING) {
        fill(dc, 40, 404, 880, 3, LINE);
        fill(dc, 40, 404, 880 * std::clamp(percent, 0, 100) / 100, 3, CYAN);
    }
    std::wstring label;
    bool enabled = true;
    switch (status) {
    case READY: label = L"PLAY DISRUPTOR"; break;
    case NEEDS_BUILD: label = L"BUILD THE GAME"; break;
    case BUILD_FAILED: label = L"TRY THE BUILD AGAIN"; break;
    case BUILDING: label = L"BUILDING...  " + std::to_wstring(percent) + L"%"; enabled = false; break;
    case CHECKING: label = L"CHECKING DISC..."; enabled = false; break;
    case RUNNING: label = L"GAME RUNNING"; enabled = false; break;
    case BAD_DISC: label = L"DISC NEEDS ATTENTION"; enabled = false; break;
    }
    button(dc, 40, 424, 880, 64, label, H_PLAY, true, enabled);
    const wchar_t* labels[] = {L"Settings", L"Controls", L"Saves folder", L"Logs folder"};
    int ids[] = {H_SETTINGS, H_CONTROLS, H_SAVES, H_LOGS};
    for (int i = 0; i < 4; ++i) button(dc, 40 + i * 225, 508, 205, 46, labels[i], ids[i], false);
    text(dc, L"VERSION " RELEASE_VERSION_W, 40, 594, 400, 20, fontTiny, DIM);
    text(dc, L"Unofficial fan project. No game data is included; it is built from your disc.", 380, 594, 540, 20, fontTiny, DIM,
         DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
}

std::vector<int> rowsOf(int cat) {
    std::vector<int> out;
    for (size_t i = 0; i < settings.size(); ++i) if (settings[i].category == cat) out.push_back(int(i));
    return out;
}

void paintSettings(HDC dc) {
    header(dc, L"Settings", L"Changes are saved as you make them and apply the next time the game starts.");
    for (int c = 0; c < 5; ++c) {
        int y = 140 + c * 46;
        bool active = c == category;
        if (active || isHot(H_CATEGORY, c)) fill(dc, 40, y, 190, 40, active ? PANEL : RGB(17, 24, 33));
        if (active) fill(dc, 40, y, 3, 40, CYAN);
        text(dc, CATEGORIES[c], 58, y, 170, 40, fontBody, active ? INK : MUTED);
        hit(40, y, 190, 40, H_CATEGORY, c);
    }
    auto rows = rowsOf(category);
    row = std::clamp(row, 0, int(rows.size()) - 1);
    const int x = 250, w = 670, rh = 36;
    for (int i = 0; i < int(rows.size()); ++i) {
        Setting& s = settings[size_t(rows[size_t(i)])];
        int y = 140 + i * rh;
        bool sel = i == row;
        if (sel) fill(dc, x, y, w, rh - 2, PANEL_HI);
        else if (isHot(H_ROW, i)) fill(dc, x, y, w, rh - 2, RGB(17, 24, 33));
        if (sel) fill(dc, x, y, 3, rh - 2, CYAN);
        text(dc, s.label, x + 18, y, 360, rh - 2, fontBody, INK);
        hit(x, y, w, rh - 2, H_ROW, i);
        int cx = x + w - 270, cw = 254;
        if (s.action) {
            text(dc, s.options[0].label + L"  ›", cx, y, cw, rh - 2, fontBody, isHot(H_INC, i) ? CYAN : INK,
                 DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
            hit(cx, y, cw, rh - 2, H_INC, i);
        } else if (s.toggle()) {
            int px = cx + cw - 46, py = y + 8;
            bool on = s.value == 1;
            fill(dc, px, py, 46, 18, on ? CYAN : LINE);
            fill(dc, on ? px + 30 : px + 2, py + 2, 14, 14, on ? BG : MUTED);
            text(dc, on ? L"On" : L"Off", cx, y, cw - 58, rh - 2, fontSmall, on ? INK : MUTED, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
            hit(cx, y, cw, rh - 2, H_INC, i);
        } else {
            bool many = s.options.size() > 5;
            text(dc, L"‹", cx, y, 24, rh - 2, fontHeading, s.value > 0 ? (isHot(H_DEC, i) ? CYAN : MUTED) : LINE,
                 DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            text(dc, L"›", cx + cw - 24, y, 24, rh - 2, fontHeading,
                 s.value + 1 < int(s.options.size()) ? (isHot(H_INC, i) ? CYAN : MUTED) : LINE, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            text(dc, s.options[size_t(s.value)].label, cx + 24, y - (many ? 4 : 0), cw - 48, rh - 2, fontBody, INK,
                 DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            if (many) {
                int tx = cx + 60, tw = cw - 120, ty = y + rh - 9;
                fill(dc, tx, ty, tw, 2, LINE);
                fill(dc, tx, ty, tw * s.value / int(s.options.size() - 1), 2, CYAN);
            }
            hit(cx, y, cw / 2, rh - 2, H_DEC, i);
            hit(cx + cw / 2, y, cw - cw / 2, rh - 2, H_INC, i);
        }
    }
    Setting& cur = settings[size_t(rows[size_t(row)])];
    fill(dc, 250, 540, 670, 1, LINE);
    text(dc, cur.help, 250, 546, 670, 40, fontSmall, MUTED, DT_LEFT | DT_TOP | DT_WORDBREAK);
    button(dc, 40, 578, 190, 40, L"Back", H_BACK, false);
    button(dc, 730, 578, 190, 40, L"Restore defaults", H_DEFAULTS, false);
    text(dc, L"Up / Down to choose, Left / Right to change", 250, 578, 460, 40, fontTiny, DIM);
}

void paintBindings(HDC dc) {
    header(dc, L"Controls", L"Click a slot, then press a key or mouse button. Delete clears a slot, Esc cancels.");
    const int x = 40, rh = 28;
    int y0 = 138;
    text(dc, L"ACTION", x + 14, y0 - 22, 220, 20, fontTiny, DIM);
    text(dc, L"CONSOLE", x + 250, y0 - 22, 120, 20, fontTiny, DIM);
    text(dc, L"PRIMARY", x + 380, y0 - 22, 240, 20, fontTiny, DIM);
    text(dc, L"ALTERNATE", x + 630, y0 - 22, 240, 20, fontTiny, DIM);
    for (int i = 0; i < ACTION_COUNT; ++i) {
        int y = y0 + i * rh;
        if (i % 2 == 0) fill(dc, x, y, 880, rh - 2, RGB(16, 22, 30));
        text(dc, ACTIONS[i].label, x + 14, y, 230, rh - 2, fontBody, INK);
        text(dc, ACTIONS[i].button, x + 250, y, 120, rh - 2, fontSmall, MUTED);
        for (int c = 0; c < 2; ++c) {
            int bx = x + 376 + c * 250;
            bool sel = i == bindRow && c == bindCol;
            bool cap = capturing && sel;
            if (cap) fill(dc, bx, y + 1, 240, rh - 4, CYAN);
            else if (sel || isHot(H_BIND, i, c)) fill(dc, bx, y + 1, 240, rh - 4, PANEL_HI);
            if (sel && !cap) fill(dc, bx, y + 1, 3, rh - 4, CYAN);
            std::wstring label = cap ? L"Press a key or button..." : bindingLabel(bindings[i][c]);
            text(dc, label, bx + 12, y, 224, rh - 2, fontBody, cap ? BG : bindings[i][c] == "None" ? DIM : INK);
            hit(bx, y, 240, rh - 2, H_BIND, i, c);
        }
    }
    int y = y0 + ACTION_COUNT * rh + 4;
    text(dc, L"Mouse look and mouse-wheel weapon selection are switched in Settings > Controls.   "
             L"F7 savestates  /  Tab fast-forward  /  Alt+Enter fullscreen  /  F6 scanlines  /  F10 FPS  /  Keypad +/- volume",
         40, y, 880, 36, fontTiny, MUTED, DT_LEFT | DT_TOP | DT_WORDBREAK);
    button(dc, 40, 578, 190, 40, L"Back", H_BACK, false);
    button(dc, 690, 578, 230, 40, L"Restore default layout", H_BIND_DEFAULTS, false);
}

void paint(HDC dc) {
    hits.clear();
    fill(dc, 0, 0, WIDTH, HEIGHT, BG);
    SetBkMode(dc, TRANSPARENT);
    switch (page) {
    case HOME: paintHome(dc); break;
    case SETTINGS: paintSettings(dc); break;
    case BINDINGS: paintBindings(dc); break;
    }
}

// ================================================================ input
void changeSetting(int index, int delta) {
    Setting& s = settings[size_t(index)];
    if (s.action) {
        if (s.key == "bindings") { page = BINDINGS; bindRow = bindCol = 0; }
        else if (s.key == "rebuild") {
            if (status == BUILDING || status == RUNNING || status == CHECKING || status == BAD_DISC) return;
            if (MessageBoxW(window, L"Build the game again from your disc image? This takes about a minute.",
                            L"Rebuild the game", MB_OKCANCEL | MB_ICONQUESTION) == IDOK)
                startBuild();
        }
        refresh();
        return;
    }
    int n = int(s.options.size());
    s.value = s.toggle() ? 1 - s.value : std::clamp(s.value + delta, 0, n - 1);
    try { writeRuntimeSettings(); } catch (...) {
        MessageBoxW(window, L"Could not save the settings. Check that the installation folder is writable.",
                    L"Disruptor Recompiled", MB_OK | MB_ICONWARNING);
    }
    refresh();
}
void finishCapture(const std::string& name) {
    if (!capturing) return;
    capturing = false;
    if (!name.empty()) {
        // One key serves one action: clear it wherever else it was bound.
        if (name != "None")
            for (auto& b : bindings) for (auto& slot : b) if (_stricmp(slot.c_str(), name.c_str()) == 0) slot = "None";
        bindings[bindRow][bindCol] = name;
        try { saveBindings(); } catch (...) {}
    }
    refresh();
}
void activate(const Hit& h) {
    switch (h.id) {
    case H_PLAY:
        if (status == READY) {
            if (launchGame()) { status = RUNNING; }
            else MessageBoxW(window, L"The game could not be started. Run Setup again to repair the installation.",
                             L"Unable to start", MB_OK | MB_ICONERROR);
        } else if (status == NEEDS_BUILD || status == BUILD_FAILED) startBuild();
        break;
    case H_SETTINGS: case H_TAB_SETTINGS: page = SETTINGS; break;
    case H_CONTROLS: case H_TAB_CONTROLS: page = BINDINGS; capturing = false; break;
    case H_TAB_HOME: case H_BACK: page = HOME; capturing = false; break;
    case H_SAVES: openFolder(L"saves"); break;
    case H_LOGS: openFolder(L"logs"); break;
    case H_CATEGORY: category = h.a; row = 0; break;
    case H_ROW: row = h.a; break;
    case H_DEC: row = h.a; changeSetting(rowsOf(category)[size_t(h.a)], -1); break;
    case H_INC: row = h.a; changeSetting(rowsOf(category)[size_t(h.a)], +1); break;
    case H_DEFAULTS:
        for (int i : rowsOf(category)) settings[size_t(i)].value = settings[size_t(i)].def;
        try { writeRuntimeSettings(); } catch (...) {}
        break;
    case H_BIND: bindRow = h.a; bindCol = h.b; capturing = true; captureArmed = false; break;
    case H_BIND_DEFAULTS:
        if (MessageBoxW(window, L"Restore the default keyboard and mouse layout?", L"Controls", MB_OKCANCEL | MB_ICONQUESTION) == IDOK)
            restoreDefaultBindings();
        break;
    }
    refresh();
}
const Hit* hitAt(int px, int py) {
    int x = MulDiv(px, 96, int(dpi)), y = MulDiv(py, 96, int(dpi));
    for (auto it = hits.rbegin(); it != hits.rend(); ++it)
        if (x >= it->r.left && x < it->r.right && y >= it->r.top && y < it->r.bottom) return &*it;
    return nullptr;
}
bool key(WPARAM vk, LPARAM lp) {
    if (capturing) {
        if (vk == VK_ESCAPE) { capturing = false; refresh(); return true; }
        if (vk == VK_DELETE || vk == VK_BACK) { finishCapture("None"); return true; }
        UINT scan = (lp >> 16) & 0xFF;
        bool ext = (lp >> 24) & 1;
        std::string name = keyName(scan, ext);
        if (!name.empty()) finishCapture(name);
        return true;
    }
    if (page == HOME) {
        if (vk == VK_RETURN || vk == VK_SPACE) { Hit h{{}, H_PLAY, 0, 0}; activate(h); return true; }
        return false;
    }
    if (vk == VK_ESCAPE) { page = HOME; refresh(); return true; }
    if (page == SETTINGS) {
        auto rows = rowsOf(category);
        switch (vk) {
        case VK_UP: row = std::max(0, row - 1); break;
        case VK_DOWN: row = std::min(int(rows.size()) - 1, row + 1); break;
        case VK_PRIOR: category = std::max(0, category - 1); row = 0; break;
        case VK_NEXT: case VK_TAB: category = (category + 1) % 5; row = 0; break;
        case VK_LEFT: changeSetting(rows[size_t(row)], -1); return true;
        case VK_RIGHT: case VK_RETURN: case VK_SPACE: changeSetting(rows[size_t(row)], +1); return true;
        default: return false;
        }
        refresh();
        return true;
    }
    if (page == BINDINGS) {
        switch (vk) {
        case VK_UP: bindRow = std::max(0, bindRow - 1); break;
        case VK_DOWN: bindRow = std::min(ACTION_COUNT - 1, bindRow + 1); break;
        case VK_LEFT: bindCol = 0; break;
        case VK_RIGHT: bindCol = 1; break;
        case VK_RETURN: case VK_SPACE: capturing = true; captureArmed = true; break;
        case VK_DELETE: case VK_BACK: bindings[bindRow][bindCol] = "None"; try { saveBindings(); } catch (...) {} break;
        default: return false;
        }
        refresh();
        return true;
    }
    return false;
}

// ================================================================ window
void createFonts() {
    auto font = [](int size, int weight) {
        return CreateFontW(-size, 0, 0, 0, weight, FALSE, FALSE, FALSE, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    };
    fontTitle = font(64, FW_BOLD);
    fontHuge = font(34, FW_SEMIBOLD);
    fontHeading = font(21, FW_SEMIBOLD);
    fontBody = font(16, FW_NORMAL);
    fontSmall = font(14, FW_NORMAL);
    fontTiny = font(12, FW_NORMAL);
}

void onVerified(bool ok) {
    if (!ok) status = BAD_DISC;
    else status = gameBuilt() ? READY : NEEDS_BUILD;
    refresh();
}

LRESULT CALLBACK wndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: SetTimer(hwnd, 1, 500, nullptr); return 0;
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps{};
        HDC dc = BeginPaint(hwnd, &ps);
        RECT client;
        GetClientRect(hwnd, &client);
        HDC mem = CreateCompatibleDC(dc);
        HBITMAP bmp = CreateCompatibleBitmap(dc, client.right, client.bottom);
        auto oldBmp = SelectObject(mem, bmp);
        int saved = SaveDC(mem);
        SetMapMode(mem, MM_ANISOTROPIC);
        SetWindowExtEx(mem, 96, 96, nullptr);
        SetViewportExtEx(mem, int(dpi), int(dpi), nullptr);
        paint(mem);
        RestoreDC(mem, saved);
        BitBlt(dc, 0, 0, client.right, client.bottom, mem, 0, 0, SRCCOPY);
        SelectObject(mem, oldBmp);
        DeleteObject(bmp);
        DeleteDC(mem);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_DPICHANGED: {
        dpi = HIWORD(wp);
        auto* r = (RECT*)lp;
        SetWindowPos(hwnd, nullptr, r->left, r->top, r->right - r->left, r->bottom - r->top, SWP_NOZORDER | SWP_NOACTIVATE);
        refresh();
        return 0;
    }
    case WM_MOUSEMOVE: {
        const Hit* h = hitAt(GET_X_LPARAM(lp), GET_Y_LPARAM(lp));
        int id = h ? h->id : -1, a = h ? h->a : -1, b = h ? h->b : -1;
        if (id != hot || a != hotA || b != hotB) { hot = id; hotA = a; hotB = b; refresh(); }
        TRACKMOUSEEVENT t{sizeof(t), TME_LEAVE, hwnd, 0};
        TrackMouseEvent(&t);
        SetCursor(LoadCursor(nullptr, h ? IDC_HAND : IDC_ARROW));
        return 0;
    }
    case WM_MOUSELEAVE: hot = hotA = hotB = -1; pressed = -1; refresh(); return 0;
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT) return TRUE;  // set in WM_MOUSEMOVE
        break;
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN: case WM_MBUTTONDOWN: case WM_XBUTTONDOWN: {
        if (capturing && captureArmed) {
            std::string name = msg == WM_LBUTTONDOWN ? "Mouse1" : msg == WM_MBUTTONDOWN ? "Mouse2" :
                               msg == WM_RBUTTONDOWN ? "Mouse3" : GET_XBUTTON_WPARAM(wp) == XBUTTON1 ? "Mouse4" : "Mouse5";
            finishCapture(name);
            swallowUp = msg == WM_LBUTTONDOWN;
            return msg == WM_XBUTTONDOWN ? TRUE : 0;
        }
        if (msg == WM_LBUTTONDOWN) {
            const Hit* h = hitAt(GET_X_LPARAM(lp), GET_Y_LPARAM(lp));
            pressed = h ? h->id : -1;
            SetCapture(hwnd);
            refresh();
        }
        return msg == WM_XBUTTONDOWN ? TRUE : 0;
    }
    case WM_LBUTTONUP: {
        ReleaseCapture();
        if (swallowUp) { swallowUp = false; return 0; }  // release of a click that was just bound
        const Hit* h = hitAt(GET_X_LPARAM(lp), GET_Y_LPARAM(lp));
        int was = pressed;
        pressed = -1;
        if (h && h->id == was) {
            Hit copy = *h;
            activate(copy);
            if (capturing) captureArmed = true;  // the click that opened the slot is over
        }
        refresh();
        return 0;
    }
    case WM_MOUSEWHEEL:
        if (capturing && captureArmed) { finishCapture(GET_WHEEL_DELTA_WPARAM(wp) > 0 ? "MouseWheelUp" : "MouseWheelDown"); return 0; }
        if (page == SETTINGS) { key(GET_WHEEL_DELTA_WPARAM(wp) > 0 ? VK_UP : VK_DOWN, 0); return 0; }
        break;
    case WM_KEYDOWN: case WM_SYSKEYDOWN:
        if (capturing && !captureArmed) captureArmed = true;
        if (key(wp, lp)) return 0;
        break;
    case WM_SYSCHAR: if (capturing) return 0; break;  // no beep / menu for Alt while binding
    case MSG_VERIFY_PROGRESS: percent = int(wp); refresh(); return 0;
    case MSG_VERIFIED: onVerified(wp != 0); return 0;
    case MSG_BUILD: {
        std::unique_ptr<std::wstring> text((std::wstring*)lp);
        if (int(wp) < 0) buildError = *text;
        else { percent = int(wp); buildText = *text; }
        refresh();
        return 0;
    }
    case MSG_BUILD_DONE:
        if (buildThread.joinable()) buildThread.join();
        builder.reset();
        if (wp == 0 && gameBuilt()) { status = READY; percent = 100; }
        else {
            status = BUILD_FAILED;
            if (buildError.empty()) buildError = L"see the build log in the Logs folder.";
        }
        refresh();
        return 0;
    case WM_TIMER:
        if (gameProcess && WaitForSingleObject(gameProcess, 0) == WAIT_OBJECT_0) {
            DWORD result = 0;
            GetExitCodeProcess(gameProcess, &result);
            CloseHandle(gameProcess);
            gameProcess = nullptr;
            status = gameBuilt() ? READY : NEEDS_BUILD;
            refresh();
            if (result) MessageBoxW(hwnd, L"The game stopped unexpectedly. The Logs folder has the details. Your saves are kept separately.",
                                    L"Disruptor Recompiled", MB_OK | MB_ICONWARNING);
            if (closeAfterGame) DestroyWindow(hwnd);
        }
        return 0;
    case WM_CLOSE:
        // Keep ownership while the game writes this profile; opening the launcher
        // again restores this window rather than starting a second game.
        if (gameProcess) { closeAfterGame = true; ShowWindow(hwnd, SW_HIDE); return 0; }
        if (status == BUILDING &&
            MessageBoxW(hwnd, L"Stop building the game? You can start the build again later.", L"Disruptor Recompiled",
                        MB_OKCANCEL | MB_ICONQUESTION) != IDOK)
            return 0;
        DestroyWindow(hwnd);
        return 0;
    case WM_SHOWWINDOW: if (wp) closeAfterGame = false; break;
    case WM_DESTROY: cancelVerify = true; PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// Paints one page offscreen to a 24-bit BMP (documentation screenshots).
bool screenshot(const std::wstring& which, const fs::path& path, int scaleDpi) {
    page = which == L"settings" ? SETTINGS : which == L"controls" ? BINDINGS : HOME;
    if (page == SETTINGS) { category = GRAPHICS; row = 1; }
    if (page == BINDINGS) { bindRow = 6; bindCol = 0; }
    status = READY;
    dpi = UINT(scaleDpi);
    int w = MulDiv(WIDTH, scaleDpi, 96), h = MulDiv(HEIGHT, scaleDpi, 96);
    BITMAPINFO bi{};
    bi.bmiHeader = {sizeof(BITMAPINFOHEADER), w, -h, 1, 32, BI_RGB, 0, 0, 0, 0, 0};
    void* bits = nullptr;
    HDC dc = CreateCompatibleDC(nullptr);
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    if (!bmp) { DeleteDC(dc); return false; }
    auto old = SelectObject(dc, bmp);
    SetMapMode(dc, MM_ANISOTROPIC);
    SetWindowExtEx(dc, 96, 96, nullptr);
    SetViewportExtEx(dc, scaleDpi, scaleDpi, nullptr);
    paint(dc);
    GdiFlush();
    BITMAPFILEHEADER fh{0x4d42, DWORD(sizeof(fh) + sizeof(BITMAPINFOHEADER) + DWORD(w) * DWORD(h) * 4), 0, 0,
                        DWORD(sizeof(fh) + sizeof(BITMAPINFOHEADER))};
    std::ofstream out(path, std::ios::binary);
    out.write((char*)&fh, sizeof(fh));
    out.write((char*)&bi.bmiHeader, sizeof(bi.bmiHeader));
    out.write((char*)bits, std::streamsize(size_t(w) * size_t(h) * 4));
    bool ok = bool(out);
    SelectObject(dc, old);
    DeleteObject(bmp);
    DeleteDC(dc);
    return ok;
}

// Bounded, silent installation smoke test. Uses only its explicit, new profile folder.
int smokeTest(const fs::path& profile, int seconds) {
    if (seconds < 1 || seconds > 180) return 3;
    userData = fs::absolute(profile);
    if (fs::exists(userData)) return 3;  // never open an existing player's profile
    if (!verifyDisc(root / L"disc" / L"Disruptor.bin")) return 2;
    if (!gameBuilt()) return 6;
    loadSettings();
    if (!launchGame(true)) return 4;
    DWORD result = WaitForSingleObject(gameProcess, DWORD(seconds) * 1000);
    if (result != WAIT_TIMEOUT) { CloseHandle(gameProcess); return 5; }
    TerminateProcess(gameProcess, 0);
    WaitForSingleObject(gameProcess, 5000);
    CloseHandle(gameProcess);
    return 0;
}

}  // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, LPWSTR, int show) {
    try {
        int argc = 0;
        LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
        std::vector<std::wstring> args(argv, argv + argc);
        LocalFree(argv);
        root = executablePath().parent_path();
        gameDir = root / L"game";
        defineSettings();
        if (argc == 3 && args[1] == L"--verify-only") return verifyDisc(args[2]) ? 0 : 2;
        if (argc == 4 && args[1] == L"--smoke-test") return smokeTest(args[2], std::stoi(args[3]));
        if (argc == 4 && args[1] == L"--screenshot") {
            loadSettings();
            loadBindings();
            createFonts();
            return screenshot(args[2], args[3], 144) ? 0 : 2;
        }
        if (argc > 1) return 3;
        userData = userDataPath();
        loadSettings();
        loadBindings();

        HANDLE single = CreateMutexW(nullptr, FALSE, L"Local\\DisruptorRecompiled.Launcher");
        if (!single) return 4;
        if (GetLastError() == ERROR_ALREADY_EXISTS) {
            if (HWND existing = FindWindowW(L"DisruptorRecompiledLauncher", nullptr)) {
                ShowWindow(existing, SW_RESTORE);
                SetForegroundWindow(existing);
            }
            CloseHandle(single);
            return 0;
        }
        createFonts();
        WNDCLASSEXW wc{sizeof(wc)};
        wc.lpfnWndProc = wndProc;
        wc.hInstance = instance;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.lpszClassName = L"DisruptorRecompiledLauncher";
        wc.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1));
        wc.hIconSm = wc.hIcon;
        RegisterClassExW(&wc);
        dpi = GetDpiForSystem();
        RECT rect{0, 0, MulDiv(WIDTH, int(dpi), 96), MulDiv(HEIGHT, int(dpi), 96)};
        DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
        AdjustWindowRectExForDpi(&rect, style, FALSE, 0, dpi);
        window = CreateWindowExW(0, wc.lpszClassName, L"Disruptor Recompiled", style, CW_USEDEFAULT, CW_USEDEFAULT,
                                 rect.right - rect.left, rect.bottom - rect.top, nullptr, nullptr, instance, nullptr);
        if (!window) return 4;
        dpi = GetDpiForWindow(window);
        BOOL dark = TRUE;
        DwmSetWindowAttribute(window, 20, &dark, sizeof(dark));
        ShowWindow(window, show);
        UpdateWindow(window);
        verifier = std::thread([] {
            bool ok = verifyDisc(root / L"disc" / L"Disruptor.bin", window);
            if (!cancelVerify) PostMessageW(window, MSG_VERIFIED, ok, 0);
        });
        MSG m{};
        while (GetMessageW(&m, nullptr, 0, 0) > 0) { TranslateMessage(&m); DispatchMessageW(&m); }
        cancelVerify = true;
        if (verifier.joinable()) verifier.join();
        if (builder) builder->kill();
        if (buildThread.joinable()) buildThread.join();
        if (gameProcess) CloseHandle(gameProcess);
        CloseHandle(single);
        return 0;
    } catch (...) {
        cancelVerify = true;
        if (verifier.joinable()) verifier.join();
        return 4;
    }
}
