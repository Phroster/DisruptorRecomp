cmake_minimum_required(VERSION 3.20)
project(DisruptorRecomp LANGUAGES C CXX)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 17)
if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "This project requires a 64-bit toolchain.")
endif()
set(PSXRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/psxrecomp" CACHE PATH "PSXRecomp checkout")
set(PSXRECOMP_BIOS_STEMS OpenBIOS CACHE STRING "BIOS backend" FORCE)
set(PSX_RECOMP_UI OFF CACHE BOOL "Shared launcher" FORCE)
set(PSX_NETPLAY OFF CACHE BOOL "Netplay" FORCE)
set(PSX_REWIND OFF CACHE BOOL "Rewind" FORCE)
set(PSX_ENABLE_VULKAN OFF CACHE BOOL "Vulkan renderer" FORCE)
set(PSX_PGXP_VARIANT OFF CACHE BOOL "Enhanced geometry variant" FORCE)
option(PSX_DEBUG_TOOLS "Local TCP diagnostics for baseline verification" ON)
include("${PSXRECOMP_ROOT}/runtime/runtime.cmake")
file(GLOB DISRUPTOR_GENERATED CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/generated/SLUS_002.24_full.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/generated/SLUS_002.24_full_*.c")
if(NOT DISRUPTOR_GENERATED)
    message(FATAL_ERROR "Generate the local game code first: run build.ps1.")
endif()
# PGXP: sub-pixel vertex precision and perspective-correct texturing. Compiles
# the value-propagation hooks (PGXP_* macros already present in all generated C)
# into this one target; the features themselves stay off until [video]
# geometry_correction / perspective_texturing enable them. The overlay shard
# cache is flavoured, so warm_cache.ps1 must be re-run after toggling this.
option(DISRUPTOR_PGXP "Build the PGXP precision engine into the game" ON)
set(_disruptor_pgxp "")
if(DISRUPTOR_PGXP)
    set(_disruptor_pgxp PGXP)
endif()
psxrecomp_add_runtime_target(disruptor ${_disruptor_pgxp}
    GAME_GENERATED_FULL_C ${DISRUPTOR_GENERATED}
    GAME_GENERATED_DISPATCH_C "${CMAKE_CURRENT_SOURCE_DIR}/generated/SLUS_002.24_dispatch.c"
    DEBUG_PORT 4624
    WINDOW_TITLE "Disruptor Recompiled"
    DEFAULT_GAME_CONFIG_PATH "game.toml"
    EXE_NAME "DisruptorRecompiled"
    MAX_PLAYERS 1
    PRELOADED_MODS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/mods/preloaded")

target_sources(disruptor PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src/disruptor_widescreen.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/disruptor_weapon_select.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/disruptor_fast_timing.c")

# Fast guest timing for the recompiled game code only (levels and rationale in
# src/disruptor_fast_timing.h). The generated files are not edited: the header
# is force-included in front of them. 0 keeps the framework's accurate model
# (build.ps1 -AccurateTiming).
set(DISRUPTOR_FAST_TIMING 5 CACHE STRING "Fast timing level for recompiled game code (0-5)")
set(DISRUPTOR_FAST_LOAD_CYCLES 2 CACHE STRING "Flat guest cycles per load at fast timing level 4")
if(DISRUPTOR_FAST_TIMING GREATER 0)
    set_property(SOURCE ${DISRUPTOR_GENERATED} APPEND_STRING PROPERTY COMPILE_FLAGS
        " -I\"${CMAKE_CURRENT_SOURCE_DIR}/generated\" -include \"${CMAKE_CURRENT_SOURCE_DIR}/src/disruptor_fast_timing.h\"")
    set_property(SOURCE ${DISRUPTOR_GENERATED} APPEND PROPERTY COMPILE_DEFINITIONS
        "DISRUPTOR_FAST_TIMING=${DISRUPTOR_FAST_TIMING}"
        "DISRUPTOR_FAST_LOAD_CYCLES=${DISRUPTOR_FAST_LOAD_CYCLES}u")
    message(STATUS "Disruptor: fast game timing level ${DISRUPTOR_FAST_TIMING}")
endif()

if(MINGW)
    # windres re-quotes inherited -I arguments incorrectly when paths contain
    # spaces. This icon-only resource has no includes or target definitions.
    get_target_property(_sources disruptor SOURCES)
    list(FILTER _sources EXCLUDE REGEX "disruptor_app_icon\\.rc$")
    set_property(TARGET disruptor PROPERTY SOURCES "${_sources}")
    set(_icon_object "${CMAKE_CURRENT_BINARY_DIR}/disruptor_icon.obj")
    add_custom_command(OUTPUT "${_icon_object}"
        COMMAND "${CMAKE_RC_COMPILER}" -O coff
            "${CMAKE_CURRENT_BINARY_DIR}/disruptor_app_icon.rc" "${_icon_object}"
        DEPENDS "${PSXRECOMP_ROOT}/assets/psxrecomp.ico"
        VERBATIM)
    set_source_files_properties("${_icon_object}" PROPERTIES EXTERNAL_OBJECT TRUE GENERATED TRUE)
    target_sources(disruptor PRIVATE "${_icon_object}")
    # Use UTF-8 consistently for runtime paths, including Windows profile names.
    # Without this, paths produced as UTF-8 cannot be reopened by narrow CRT APIs.
    set(_manifest_object "${CMAKE_CURRENT_BINARY_DIR}/disruptor_manifest.obj")
    add_custom_command(OUTPUT "${_manifest_object}"
        COMMAND "${CMAKE_RC_COMPILER}" -O coff disruptor.manifest.rc "${_manifest_object}"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/src/windows"
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/windows/disruptor.manifest.rc"
                "${CMAKE_CURRENT_SOURCE_DIR}/src/windows/disruptor.manifest"
        VERBATIM)
    set_source_files_properties("${_manifest_object}" PROPERTIES EXTERNAL_OBJECT TRUE GENERATED TRUE)
    target_sources(disruptor PRIVATE "${_manifest_object}")
endif()
