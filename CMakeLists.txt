cmake_minimum_required(VERSION 3.13.4)

project(LabUtils)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/LabUtils")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "S. Korteland (Erasmus MC)")
set(EXTENSION_DESCRIPTION "This is an example of a simple extension")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/LabUtils.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/LabUtils/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(ClipBranches)
add_subdirectory(OpenSurface)
add_subdirectory(AddFlowExtension)
add_subdirectory(PrepareModelForCFD)
add_subdirectory(CFDModelPostprocessing)
add_subdirectory(InspectVolumeWithModel)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
