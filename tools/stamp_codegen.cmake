# The overlay tests need the runtime's source hash before its first build.
get_filename_component(PSXRECOMP_CODEGEN_HASH_ROOT "${CMAKE_CURRENT_LIST_DIR}/../psxrecomp" ABSOLUTE)
include("${PSXRECOMP_CODEGEN_HASH_ROOT}/runtime/codegen_hash_sources.cmake")
set(SRCS ${PSXRECOMP_CODEGEN_HASH_SRCS})
set(OUT "${PSXRECOMP_CODEGEN_HASH_ROOT}/runtime/include/overlay_codegen_hash.h")
include("${PSXRECOMP_CODEGEN_HASH_ROOT}/runtime/hash_codegen.cmake")
