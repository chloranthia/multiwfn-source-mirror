cmake_minimum_required(VERSION 3.24)

project(Multiwfn LANGUAGES C Fortran)

include(CheckFortranCompilerFlag)

option(MULTIWFN_WITH_OPENMP "Enable OpenMP when the compiler supports it" ON)
option(MULTIWFN_WITH_FD
  "Enable fractional derivatives using FLINT"
  OFF
)
option(MULTIWFN_BUILD_GUI
  "Build the DISLIN GUI executable instead of the no-GUI executable"
  OFF
)
set(MULTIWFN_GNU_OPT_LEVEL "O2" CACHE STRING "GNU Fortran optimization level for Release builds")
set(MULTIWFN_GNU_HOT_OPT_LEVEL "" CACHE STRING
  "Optional GNU Fortran optimization level for selected hot sources")
set(MULTIWFN_GNU_EXTRA_FLAGS "" CACHE STRING
  "Additional GNU Fortran flags, separated by spaces")

if(NOT MULTIWFN_GNU_OPT_LEVEL MATCHES "^O[0-3s]$")
  message(FATAL_ERROR "MULTIWFN_GNU_OPT_LEVEL must be one of O0, O1, O2, O3, or Os")
endif()
if(MULTIWFN_GNU_HOT_OPT_LEVEL AND NOT MULTIWFN_GNU_HOT_OPT_LEVEL MATCHES "^O[0-3s]$")
  message(FATAL_ERROR
    "MULTIWFN_GNU_HOT_OPT_LEVEL must be empty or one of O0, O1, O2, O3, or Os")
endif()

set(MULTIWFN_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")
include(cmake/prepare_frj_source.cmake)
set(CMAKE_Fortran_MODULE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/mod")
set(CMAKE_Fortran_PREPROCESS ON)

if(APPLE)
  include(CheckLinkerFlag)
  foreach(lang C Fortran)
    if(CMAKE_${lang}_COMPILER_ID STREQUAL "GNU")
      check_linker_flag(${lang} "-nodefaultrpaths"
        MULTIWFN_${lang}_HAS_NODEFAULTRPATHS)
      if(MULTIWFN_${lang}_HAS_NODEFAULTRPATHS)
        # Recent GCC drivers add runtime paths that CMake can also emit.
        # Let CMake own RPATHs, retaining compiler paths for build-tree tests.
        add_link_options("$<$<LINK_LANGUAGE:${lang}>:-nodefaultrpaths>")
        foreach(directory IN LISTS CMAKE_${lang}_IMPLICIT_LINK_DIRECTORIES)
          file(REAL_PATH "${directory}" runtime_directory)
          list(APPEND CMAKE_BUILD_RPATH "${runtime_directory}")
        endforeach()
      endif()
    endif()
  endforeach()
  list(REMOVE_DUPLICATES CMAKE_BUILD_RPATH)
endif()

function(multiwfn_link_fortran_libraries target)
  set(linked_frameworks "")
  foreach(library IN LISTS ARGN)
    if(APPLE AND library MATCHES "^(.+)/([^/]+)\\.framework(/.*)?$")
      set(framework_directory "${CMAKE_MATCH_1}")
      set(framework_name "${CMAKE_MATCH_2}")
      if(NOT library IN_LIST linked_frameworks)
        list(APPEND linked_frameworks "${library}")
        # Full framework paths make CMake add C header flags to Fortran.
        # Preserve the discovered search path only for the linker.
        target_link_options(${target} PRIVATE
          "SHELL:-F \"${framework_directory}\"")
        target_link_libraries(${target} PRIVATE
          "$<LINK_LIBRARY:FRAMEWORK,${framework_name}>")
      endif()
    else()
      target_link_libraries(${target} PRIVATE "${library}")
    endif()
  endforeach()
endfunction()

if(MULTIWFN_BUILD_GUI
    AND NOT WIN32
    AND NOT CMAKE_SYSTEM_NAME STREQUAL "Linux"
    AND NOT APPLE)
  message(FATAL_ERROR
    "The GUI build is currently configured for Linux, macOS, and Windows only")
endif()

find_package(BLAS REQUIRED)
find_package(LAPACK REQUIRED)

if(MULTIWFN_BUILD_GUI)
  set(MULTIWFN_DISLIN_LIBRARY "" CACHE FILEPATH
    "Platform-specific DISLIN library used by the GUI build")
  if(NOT MULTIWFN_DISLIN_LIBRARY OR NOT EXISTS "${MULTIWFN_DISLIN_LIBRARY}")
    message(FATAL_ERROR
      "Set MULTIWFN_DISLIN_LIBRARY to an existing platform-specific DISLIN library")
  endif()

  set(MULTIWFN_TARGET Multiwfn)
  set(MULTIWFN_GRAPHICS_SOURCES
    "${MULTIWFN_SOURCE_DIR}/dislin_d.f90"
    "${MULTIWFN_SOURCE_DIR}/mouse_rotate.f90"
  )
  if(WIN32)
    # The Win32 POINT type conflicts with DISLIN's point procedure when both
    # modules are imported by GUI.f90. Keep the synchronized sources unchanged.
    set_property(SOURCE "${MULTIWFN_SOURCE_DIR}/mouse_rotate.f90" APPEND PROPERTY
      COMPILE_DEFINITIONS "POINT=MultiwfnWin32Point")
    set(MULTIWFN_GUI_PLATFORM_LIBRARIES opengl32 gdi32 user32)
  else()
    list(APPEND MULTIWFN_GRAPHICS_SOURCES "${MULTIWFN_SOURCE_DIR}/ext/xlib.f90")
    find_package(X11 REQUIRED)
    find_package(OpenGL REQUIRED)
    find_library(MULTIWFN_MOTIF_LIBRARY NAMES Xm REQUIRED)
    find_library(MULTIWFN_XT_LIBRARY NAMES Xt REQUIRED)
    set(MULTIWFN_GUI_PLATFORM_LIBRARIES
      "${MULTIWFN_MOTIF_LIBRARY}"
      "${MULTIWFN_XT_LIBRARY}"
      X11::X11
    )
    if(APPLE)
      list(APPEND MULTIWFN_GUI_PLATFORM_LIBRARIES "${OPENGL_gl_LIBRARY}")
    else()
      list(APPEND MULTIWFN_GUI_PLATFORM_LIBRARIES OpenGL::GL)
    endif()
  endif()
else()
  set(MULTIWFN_DISLIN_MODULE "${CMAKE_CURRENT_SOURCE_DIR}/cmake/dislin_mod_empty.f90"
    CACHE FILEPATH "DISLIN module used by the noGUI build")
  if(NOT EXISTS "${MULTIWFN_DISLIN_MODULE}")
    message(FATAL_ERROR "MULTIWFN_DISLIN_MODULE does not exist: ${MULTIWFN_DISLIN_MODULE}")
  endif()
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  set(MULTIWFN_TARGET Multiwfn_noGUI)
  set(MULTIWFN_GRAPHICS_SOURCES
    "${MULTIWFN_DISLIN_MODULE}"
    "${MULTIWFN_SOURCE_DIR}/noGUI/dislin_d_empty.f90"
    "${MULTIWFN_SOURCE_DIR}/noGUI/mouse_rotate_empty.f90"
  )
endif()

if(MULTIWFN_WITH_OPENMP)
  find_package(OpenMP COMPONENTS Fortran)
  if(NOT OpenMP_Fortran_FOUND)
    message(WARNING "OpenMP was requested but not found; continuing with serial code")
  endif()
endif()

if(MULTIWFN_WITH_FD)
  set(MULTIWFN_FD_ENABLED ON)
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(MULTIWFN_FLINT REQUIRED IMPORTED_TARGET flint>=3)
  set(MULTIWFN_2F2_C_SOURCE "${MULTIWFN_SOURCE_DIR}/ext/2F2.c")
  find_library(MULTIWFN_FLINT_LIBRARY NAMES flint
    HINTS ${MULTIWFN_FLINT_LIBRARY_DIRS} REQUIRED)
  # Ubuntu 24.04's flint.pc lists GMP and MPFR but omits FLINT itself.
  set(MULTIWFN_FD_LIBRARIES
    "${MULTIWFN_FLINT_LIBRARY}" PkgConfig::MULTIWFN_FLINT)
  set(MULTIWFN_FD_INCLUDE_DIRS ${MULTIWFN_FLINT_INCLUDE_DIRS})
else()
  set(MULTIWFN_FD_ENABLED OFF)
  set(MULTIWFN_2F2_C_SOURCE "${MULTIWFN_SOURCE_DIR}/ext/no2F2.c")
endif()

set(MULTIWFN_SOURCE_VERSION "unknown" CACHE STRING
  "Source revision recorded in installed build metadata")
if(MULTIWFN_SOURCE_VERSION STREQUAL "unknown")
  find_package(Git QUIET)
  if(Git_FOUND)
    execute_process(
      COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}" rev-parse --verify HEAD
      OUTPUT_VARIABLE MULTIWFN_GIT_REVISION
      OUTPUT_STRIP_TRAILING_WHITESPACE
      ERROR_QUIET
      RESULT_VARIABLE MULTIWFN_GIT_RESULT
    )
    if(MULTIWFN_GIT_RESULT EQUAL 0 AND MULTIWFN_GIT_REVISION)
      set(MULTIWFN_SOURCE_VERSION "${MULTIWFN_GIT_REVISION}")
    endif()
  endif()
endif()

string(JOIN " " MULTIWFN_BLAS_LIBRARIES_METADATA ${BLAS_LIBRARIES})
string(JOIN " " MULTIWFN_LAPACK_LIBRARIES_METADATA ${LAPACK_LIBRARIES})
if(MULTIWFN_WITH_OPENMP AND OpenMP_Fortran_FOUND)
  set(MULTIWFN_OPENMP_ENABLED ON)
else()
  set(MULTIWFN_OPENMP_ENABLED OFF)
endif()
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/cmake/build-metadata.txt.in"
  "${CMAKE_CURRENT_BINARY_DIR}/build-metadata.txt"
  @ONLY
)

if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  # The upstream sources use legacy Fortran syntax and very long free-form lines.
  # Probe compatibility flags because older GNU Fortran versions do not accept all
  # flags supported by current runners.
  set(MULTIWFN_GNU_FLAGS
    -ffree-line-length-none
    -std=legacy
  )
  foreach(flag IN ITEMS -fallow-argument-mismatch -fallow-invalid-boz)
    string(MAKE_C_IDENTIFIER "${flag}" flag_id)
    check_fortran_compiler_flag("${flag}" "MULTIWFN_SUPPORTS_${flag_id}")
    if(MULTIWFN_SUPPORTS_${flag_id})
      list(APPEND MULTIWFN_GNU_FLAGS "${flag}")
    endif()
  endforeach()
  if(MULTIWFN_GNU_EXTRA_FLAGS)
    separate_arguments(MULTIWFN_GNU_EXTRA_FLAGS_LIST NATIVE_COMMAND
      "${MULTIWFN_GNU_EXTRA_FLAGS}")
    list(APPEND MULTIWFN_GNU_FLAGS ${MULTIWFN_GNU_EXTRA_FLAGS_LIST})
  endif()
  foreach(flag IN LISTS MULTIWFN_GNU_FLAGS)
    add_compile_options($<$<COMPILE_LANGUAGE:Fortran>:${flag}>)
  endforeach()

  foreach(config_var IN ITEMS CMAKE_Fortran_FLAGS_RELEASE CMAKE_Fortran_FLAGS_RELWITHDEBINFO)
    string(REGEX REPLACE "(^| )-O[0-3s]( |$)" " -${MULTIWFN_GNU_OPT_LEVEL} "
      "${config_var}" "${${config_var}}")
    string(STRIP "${${config_var}}" "${config_var}")
  endforeach()
endif()

# DFTxclib.F is fixed-form Fortran whose continuation lines begin with '#'.
# Passing that file through cpp turns valid Fortran into invalid directives.
set_source_files_properties(
  "${MULTIWFN_SOURCE_DIR}/DFTxclib.F"
  PROPERTIES Fortran_PREPROCESS OFF
)

set(MULTIWFN_SOURCES
  ${MULTIWFN_GRAPHICS_SOURCES}
  "${MULTIWFN_SOURCE_DIR}/define.f90"
  "${MULTIWFN_SOURCE_DIR}/util.f90"
  "${MULTIWFN_SOURCE_DIR}/plot.f90"
  "${MULTIWFN_SOURCE_DIR}/Bspline.f90"
  "${MULTIWFN_SOURCE_DIR}/sym.F"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/libreta.f90"
  "${MULTIWFN_SOURCE_DIR}/function.f90"
  "${MULTIWFN_SOURCE_DIR}/GUI.f90"
  "${MULTIWFN_SOURCE_DIR}/sub.f90"
  "${MULTIWFN_SOURCE_DIR}/integral.f90"
  "${MULTIWFN_SOURCE_DIR}/Lebedev-Laikov.F"
  "${MULTIWFN_SOURCE_DIR}/DFTxclib.F"
  "${MULTIWFN_SOURCE_DIR}/edflib.f90"
  "${MULTIWFN_SOURCE_DIR}/fparser.f90"
  "${MULTIWFN_SOURCE_DIR}/fileIO.f90"
  "${MULTIWFN_SOURCE_DIR}/spectrum.f90"
  "${MULTIWFN_SOURCE_DIR}/DOS.f90"
  "${MULTIWFN_SOURCE_DIR}/Multiwfn.f90"
  "${MULTIWFN_SOURCE_DIR}/0123dim.f90"
  "${MULTIWFN_SOURCE_DIR}/LSB.f90"
  "${MULTIWFN_SOURCE_DIR}/population.f90"
  "${MULTIWFN_FRJ_SOURCE}"
  "${MULTIWFN_SOURCE_DIR}/orbcomp.f90"
  "${MULTIWFN_SOURCE_DIR}/bondorder.f90"
  "${MULTIWFN_SOURCE_DIR}/topology.f90"
  "${MULTIWFN_SOURCE_DIR}/excittrans.f90"
  "${MULTIWFN_SOURCE_DIR}/otherfunc.f90"
  "${MULTIWFN_SOURCE_DIR}/otherfunc2.f90"
  "${MULTIWFN_SOURCE_DIR}/otherfunc3.f90"
  "${MULTIWFN_SOURCE_DIR}/O1.f90"
  "${MULTIWFN_SOURCE_DIR}/surfana.f90"
  "${MULTIWFN_SOURCE_DIR}/procgriddata.f90"
  "${MULTIWFN_SOURCE_DIR}/AdNDP.f90"
  "${MULTIWFN_SOURCE_DIR}/fuzzy.f90"
  "${MULTIWFN_SOURCE_DIR}/CDA.f90"
  "${MULTIWFN_SOURCE_DIR}/basin.f90"
  "${MULTIWFN_SOURCE_DIR}/orbloc.f90"
  "${MULTIWFN_SOURCE_DIR}/visweak.f90"
  "${MULTIWFN_SOURCE_DIR}/EDA.f90"
  "${MULTIWFN_SOURCE_DIR}/CDFT.f90"
  "${MULTIWFN_SOURCE_DIR}/ETS_NOCV.f90"
  "${MULTIWFN_SOURCE_DIR}/atmraddens.f90"
  "${MULTIWFN_SOURCE_DIR}/NAONBO.f90"
  "${MULTIWFN_SOURCE_DIR}/grid.f90"
  "${MULTIWFN_SOURCE_DIR}/PBC.f90"
  "${MULTIWFN_SOURCE_DIR}/hyper_polar.f90"
  "${MULTIWFN_SOURCE_DIR}/deloc_aromat.f90"
  "${MULTIWFN_SOURCE_DIR}/cp2kmate.f90"
  "${MULTIWFN_SOURCE_DIR}/minpack.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/blockhrr_012345.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/ean.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/hrr_012345.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/eanvrr_012345.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/boysfunc.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/naiveeri.f90"
  "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/ryspoly.f90"
  "${MULTIWFN_SOURCE_DIR}/ext/2F2.f90"
  "${MULTIWFN_2F2_C_SOURCE}"
)

add_executable(${MULTIWFN_TARGET} ${MULTIWFN_SOURCES})

target_include_directories(${MULTIWFN_TARGET} PRIVATE
  "${MULTIWFN_SOURCE_DIR}"
  "${MULTIWFN_SOURCE_DIR}/ext"
)
if(MULTIWFN_WITH_FD)
  target_include_directories(${MULTIWFN_TARGET} PRIVATE
    ${MULTIWFN_FD_INCLUDE_DIRS}
  )
endif()

multiwfn_link_fortran_libraries(${MULTIWFN_TARGET}
  ${BLAS_LIBRARIES}
  ${LAPACK_LIBRARIES}
)
target_link_libraries(${MULTIWFN_TARGET} PRIVATE
  ${MULTIWFN_FD_LIBRARIES}
)

if(MULTIWFN_WITH_OPENMP AND OpenMP_Fortran_FOUND)
  target_link_libraries(${MULTIWFN_TARGET} PRIVATE OpenMP::OpenMP_Fortran)
endif()

if(WIN32)
  # Make the platform branch explicit for compilers/environments that do not
  # predefine _WIN32 for Fortran preprocessing.
  target_compile_definitions(${MULTIWFN_TARGET} PRIVATE _WIN32)
endif()

if(MULTIWFN_BUILD_GUI)
  target_include_directories(${MULTIWFN_TARGET} PRIVATE
    "${MULTIWFN_SOURCE_DIR}/libreta_hybrid"
  )
  target_link_libraries(${MULTIWFN_TARGET} PRIVATE
    "${MULTIWFN_DISLIN_LIBRARY}"
  )
  multiwfn_link_fortran_libraries(${MULTIWFN_TARGET}
    ${MULTIWFN_GUI_PLATFORM_LIBRARIES}
  )
  if(MINGW)
    # The Windows GUI build needs the large stack reserve used by upstream builds.
    target_link_options(${MULTIWFN_TARGET} PRIVATE "-Wl,--stack,1900000000")
  endif()
endif()

if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  set_source_files_properties(
    "${MULTIWFN_SOURCE_DIR}/O1.f90"
    "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/blockhrr_012345.f90"
    PROPERTIES COMPILE_OPTIONS "$<$<CONFIG:Release>:-O1>"
  )
  if(MULTIWFN_GNU_HOT_OPT_LEVEL)
    set_source_files_properties(
      "${MULTIWFN_SOURCE_DIR}/function.f90"
      "${MULTIWFN_SOURCE_DIR}/grid.f90"
      "${MULTIWFN_SOURCE_DIR}/util.f90"
      "${MULTIWFN_SOURCE_DIR}/libreta_hybrid/libreta.f90"
      PROPERTIES COMPILE_OPTIONS
        "$<$<CONFIG:Release>:-${MULTIWFN_GNU_HOT_OPT_LEVEL}>"
    )
  endif()
endif()

if(UNIX AND NOT APPLE)
  set_target_properties(${MULTIWFN_TARGET} PROPERTIES
    BUILD_RPATH "$ORIGIN/lib"
    INSTALL_RPATH "$ORIGIN/lib"
  )
elseif(APPLE)
  set_target_properties(${MULTIWFN_TARGET} PROPERTIES
    BUILD_RPATH "@loader_path/lib;${CMAKE_BUILD_RPATH}"
    INSTALL_RPATH "@loader_path/lib"
  )
endif()

install(TARGETS ${MULTIWFN_TARGET} RUNTIME DESTINATION .)
install(FILES
  "${MULTIWFN_SOURCE_DIR}/settings.ini"
  "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE.txt"
  "${CMAKE_CURRENT_BINARY_DIR}/build-metadata.txt"
  DESTINATION .
)

enable_testing()

# Exercise the Fortran ABI and numerical results of every BLAS/LAPACK routine
# called by Multiwfn, including when the GUI uses a different platform backend.
add_executable(Multiwfn_blas_lapack_regression
  "${CMAKE_CURRENT_SOURCE_DIR}/tests/blas_lapack_regression.f90"
)
multiwfn_link_fortran_libraries(Multiwfn_blas_lapack_regression
  ${BLAS_LIBRARIES}
  ${LAPACK_LIBRARIES}
)
add_test(NAME Multiwfn_blas_lapack_regression COMMAND Multiwfn_blas_lapack_regression)

if(NOT MULTIWFN_BUILD_GUI)
  if(MULTIWFN_WITH_FD)
    add_executable(Multiwfn_fd_regression
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/fd_regression.c"
      "${MULTIWFN_SOURCE_DIR}/ext/2F2.c"
    )
    target_compile_features(Multiwfn_fd_regression PRIVATE c_std_99)
    target_include_directories(Multiwfn_fd_regression PRIVATE
      "${MULTIWFN_SOURCE_DIR}/ext"
      ${MULTIWFN_FD_INCLUDE_DIRS}
    )
    target_link_libraries(Multiwfn_fd_regression PRIVATE
      ${MULTIWFN_FD_LIBRARIES}
    )
    add_test(NAME Multiwfn_fd_regression COMMAND Multiwfn_fd_regression)
  endif()

  add_test(
    NAME Multiwfn_noGUI_functional
    COMMAND ${CMAKE_COMMAND} -E env
      OMP_NUM_THREADS=1
      OPENBLAS_NUM_THREADS=1
      OMP_STACKSIZE=64M
      KMP_STACKSIZE=64M
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_nogui_tests.py"
      "$<TARGET_FILE:${MULTIWFN_TARGET}>"
      --settings "${MULTIWFN_SOURCE_DIR}/settings.ini"
  )
  add_test(
    NAME Multiwfn_build_metadata
    COMMAND "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_build_metadata.py"
      "${CMAKE_CURRENT_BINARY_DIR}/build-metadata.txt"
  )
endif()
