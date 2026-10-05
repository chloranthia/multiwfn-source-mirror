set(MULTIWFN_FRJ_SOURCE "${MULTIWFN_SOURCE_DIR}/ext/frj.f90")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${MULTIWFN_FRJ_SOURCE}"
)
file(READ "${MULTIWFN_FRJ_SOURCE}" frj_source)

# STATUS='replace' requires FILE=. Preserve the upstream fort.81 output while
# keeping src/ an unmodified mirror of the downloaded source archive.
set(frj_space "[ \t\r\n&]*")
set(frj_replace_status "[rR][eE][pP][lL][aA][cC][eE]")
# Anchor at a statement's line start to exclude comments and quoted examples.
# Only the known two-argument OPEN is adapted; FILE= or other units stay intact.
string(CONCAT frj_open_pattern
  "((^|\n)[ \t]*([0-9]+[ \t]+)?)[oO][pP][eE][nN]${frj_space}\\("
  "${frj_space}([uU][nN][iI][tT]${frj_space}=${frj_space})?81${frj_space},${frj_space}"
  "[sS][tT][aA][tT][uU][sS]${frj_space}=${frj_space}"
  "('${frj_replace_status}'|\"${frj_replace_status}\")${frj_space}\\)"
)
string(REGEX REPLACE "${frj_open_pattern}"
  "\\1open(81,file=\"fort.81\",status=\"replace\")"
  frj_compatible_source "${frj_source}"
)
if(NOT frj_source STREQUAL frj_compatible_source)
  set(MULTIWFN_FRJ_SOURCE "${CMAKE_CURRENT_BINARY_DIR}/compat/frj.f90")
  set(frj_generated_source "")
  if(EXISTS "${MULTIWFN_FRJ_SOURCE}")
    file(READ "${MULTIWFN_FRJ_SOURCE}" frj_generated_source)
  endif()
  # Avoid recompiling this source on unrelated CMake reconfigurations.
  if(NOT frj_generated_source STREQUAL frj_compatible_source)
    file(WRITE "${MULTIWFN_FRJ_SOURCE}" "${frj_compatible_source}")
  endif()
  message(STATUS "Building frj.f90 with an explicit fort.81 output filename")
endif()
