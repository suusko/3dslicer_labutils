# 3dslicer_labutils
This repository contains a collection of custom modules for 3D Slicer useful for the Biomechanics Lab at the Department of Biomedical Engineering, Erasmus MC, Rotterdam. Modules include geometry preparation for CFD meshing and simulation of blood flow through arteries and postprocessing of CFD results. The modules depend heavily on the vmtk library. 



# Installation
The LabUtils extension is available for recent 3D Slicer versions 5.4.0 and above. It is not yet available through Slicer's extension manager, but can be added to 3D Slicer as follows. Clone this repository to you local PC, or download the zipped code. Open 3D Slicer, and open the 'Extension Wizard' module. Select 'Select Extension' and then browse to the folder containing the LabUtils extension. Load the modules when asked.

dependendies: This extension uses the logic of the SlicerVMTK extension, which can be installed through 3D Slicer's extension manager.

# Usage
LabUtils extension provides the following modules:
- CFD pre-processing
    - [AddFlowExtension](Docs/AddFlowExtension.md): add flow extensions at the opened ends of a model geometry of a blood vessel
    - [OpenSurface](Docs/OpenSurface.md): open a geometry normal to the centerline at a location the user selects.
    - [PrepareModelForCFD](Docs/PrepareModelForCFD.md): module containing the workflow to prepare a geometry for meshing (load, compute centerline, open model surface, add flow extensions, save )
- CFD post-processing
    - [ClipBranches](Docs/ClipBranches.md): divide a surface and clip branches in relation to its split and grouped centerlines. Convenience module based on vmtkbranchclipper
    - [CFDModelPostProcessing](Docs/CFDModelPostProcessing.md): module containing the workflow to postprocess files containing CFD results (e.g. *.tec, *_tec.dat, *.vtp format): display results, remove flow extensions, clip surface to ROI, compute 2D maps and save results to file
- Analysis:
	- [InspectVolumeWithModel](Docs/InspectVolumeWithModel): module to probe a volume with a model surface. Intensity values of the volume are computed at the surface vertices by taking the mean or average of pixels in the volume that are crossed by line profiles normal to the model surface. 