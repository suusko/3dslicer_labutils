# 3dslicer_labutils
This repository contains a collection of custom modules for 3D Slicer useful for the Biomechanics Lab at the Department of Biomedical Engineering, Erasmus MC, Rotterdam. Modules include geometry preparation for CFD meshing and simulation of blood flow through arteries and postprocessing of CFD results. The modules depend heavily on the vmtk library. 

The modules are:
- AddFlowExtension: add flow extensions at the opened ends of a model geometry of a blood vessel
- ClipBranches: divide a surface and clip branches in relation to its split and grouped centerlines. Convenience module based on vmtkbranchclipper
- OpenSurface: open a geometry normal to the centerline at a location the user selects.
- PrepareModelForCFD: module containing the various steps to prepare a geometry for meshing (load, compute centerline, open model surface, add flow extensions, save )
- CFDModelPostProcessing: module containing the various steps to postprocess files containing CFD results (e.g. *.tec, *_tec.dat, *.vtp format): display results, remove flow extensions, clip surface to ROI, compute 2D maps and save results to file
