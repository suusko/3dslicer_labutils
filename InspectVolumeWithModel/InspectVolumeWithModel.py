import logging
import os
from typing import Annotated, Optional

import vtk
from scipy import ndimage as ndi, spatial
import numpy as np
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode
from slicer import vtkMRMLModelNode


#
# InspectVolumeWithModel
#

class InspectVolumeWithModel(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "InspectVolumeWithModel"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["LabUtils"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["S. Korteland, Dept of Biomedical Engineering, Erasmus MC, Rotterdam, The Netherlands "]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
This module can be used to extract volume information on a model surface.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """

"""



#
# InspectVolumeWithModelParameterNode
#

@parameterNodeWrapper
class InspectVolumeWithModelParameterNode:
    """
    The parameters needed by module.

    inputVolume - The volume to inspect.
    inputModel - the model to inspect the volume with
    profileLength - the length of the profile used to probe the volume normal to the input model surface
    outputModel - the model with an added array that contains the representative values of the volume at the model surface
    scalarPrefix - a string to prepend to the scalar name of the output data (to avoid overwriting the scalar name if it already exists from a previous run of the module)
    """
    inputVolume: vtkMRMLScalarVolumeNode
    inputModel: vtkMRMLModelNode
    profileLength: Annotated[int, WithinRange(0, 400)] = 180
    outputModel: vtkMRMLModelNode
    scalarPrefix: str


#
# InspectVolumeWithModelWidget
#

class InspectVolumeWithModelWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/InspectVolumeWithModel.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = InspectVolumeWithModelLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self) -> None:
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.inputVolume:
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.inputVolume = firstVolumeNode

    def setParameterNode(self, inputParameterNode: Optional[InspectVolumeWithModelParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
            self._checkCanApply()

    def _checkCanApply(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputVolume and self._parameterNode.inputModel:
            self.ui.applyButton.toolTip = "Inspect volume with model"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input and output volume and model nodes"
            self.ui.applyButton.enabled = False

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            # Compute output
            self.logic.process(self.ui.inputVolumeSelector.currentNode(), self.ui.inputModelSelector.currentNode(),
                               self.ui.profileLengthSpinBox.value, self.ui.outputModelSelector.currentNode(),self.ui.scalarPrefixLineEdit.text)

            
            print('Apply')


#
# InspectVolumeWithModelLogic
#

class InspectVolumeWithModelLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return InspectVolumeWithModelParameterNode(super().getParameterNode())

    def process(self,
                inputVolume: vtkMRMLScalarVolumeNode,
                inputModel: vtkMRMLModelNode,
                profileLength: int,
                outputModel: vtkMRMLModelNode,
                scalarPrefix: str) -> None:
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be inspected with model
        :param inputModel: surfacemodel to use to inspect volume
        :param profileLength: length of the profiles to inspect the volume with normal to the input surface model (in micrometer)
        :param scalarPrefix: string to be prepended to the name of the computed scalar output 
        """

        from vtk.numpy_interface import dataset_adapter as dsa

        if not inputVolume or not inputModel or not outputModel:
            raise ValueError("Input volume, input model, or output model is invalid")

        # rescale the image to isotropic voxel size (this is assumed by the profile_line function)
        inputSpacing = inputVolume.GetSpacing()
        minSpacing = min(inputSpacing)
        #print(minSpacing)
        isotropicInputVolume = self.resampleVolumeToIsotropicSpacing(inputVolume, minSpacing)

        # get surface nodes
        surfacePoints = dsa.WrapDataObject(inputModel.GetPolyData()).Points

        # compute vertex normals
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(inputModel.GetPolyData())
        normals.ComputePointNormalsOn()
        normals.SplittingOff()
        normals.AutoOrientNormalsOn()
        normals.Update()

        # write to file
        # outfilepath = ''
        # writer = vtk.vtkXMLPolyDataWriter()
        # writer.SetDataModeToAscii()
        # writer.SetFileName(outfilepath)
        # writer.SetInputData(normals.GetOutput())
        # writer.Write()


        # and inverted normals
        normalsFlip = vtk.vtkPolyDataNormals()
        normalsFlip.SetInputData(inputModel.GetPolyData())
        normalsFlip.ComputePointNormalsOn()
        normalsFlip.SplittingOff()
        normalsFlip.SetFlipNormals(1)
        normalsFlip.AutoOrientNormalsOn()
        normalsFlip.Update()

        # write to file
        #outfilepath = ''
        #writer = vtk.vtkXMLPolyDataWriter()
        #writer.SetDataModeToAscii()
        #writer.SetFileName(outfilepath)
        #writer.SetInputData(normalsFlip.GetOutput())
        #writer.Write()

        # to array
        normalsData = dsa.WrapDataObject(normals.GetOutput()).PointData['Normals']
        normalsFlipData = dsa.WrapDataObject(normalsFlip.GetOutput()).PointData['Normals']

        
        # Convert physical vertex coordinates to voxel IJK coords
        volumeRasToIjk = vtk.vtkMatrix4x4()
        isotropicInputVolume.GetRASToIJKMatrix(volumeRasToIjk)
        rasToIjkMatrix = slicer.util.arrayFromVTKMatrix(volumeRasToIjk)
        surfacePointsIjk = self.worldToVox(surfacePoints, rasToIjkMatrix)
        
        #print(surfacePoints[1000,:])
        #print(surfacePointsIjk[1000,:])

        # scale normals to defined profile length (in mm)
        scale = (profileLength/1000)/2
        normalsLength=np.linalg.norm(normalsData,axis=1)
        #normals_length_unit_check =np.linalg.norm(normals_unit_length,axis=1)
        normalsScaled = (normalsData)/normalsLength*scale
        #normals_length_scaled_check =np.linalg.norm(normals_scaled,axis=1)
        normalsScaledIjk = self.worldToVox(normalsScaled, rasToIjkMatrix)

        normalsFlipLength = np.linalg.norm(normalsFlipData,axis=1)
        normalsFlipScaled = normalsFlipData/normalsFlipLength*scale
        #normals_flip_length_scaled_check =np.linalg.norm(normals_flip_scaled,axis=1)
        normalsFlipScaledIjk = self.worldToVox(normalsFlipScaled, rasToIjkMatrix)

        # compute intensity values representative for the voxels, based on the scaled normals
        meanOverProfile = np.zeros((surfacePointsIjk.shape[0]))
        maxOverProfile = np.zeros((surfacePointsIjk.shape[0]))
        # get volume scalar array
        isotropicInputVolumeArray = slicer.util.arrayFromVolume(isotropicInputVolume)
        #print(f'volumeArray shape = {isotropicInputVolumeArray.shape}')
        # TODO: progressbar in logic class is perhaps not the best idea?
        progressbar= slicer.util.createProgressDialog(autoClose=True)
        progressbar.labelText = "processing"
        nPoints = len(surfacePointsIjk)

        # need imageArrayIJK
        isotropicInputVolumeArrayIJK = np.transpose(isotropicInputVolumeArray, axes=[2,1, 0])
        for (i, vtx) in enumerate(surfacePoints):
            slicer.app.processEvents()
            
            startPoint =  vtx + normalsFlipScaled[i,:]
            endPoint = vtx + normalsScaled[i,:]
            
            startPointIJK = self.worldToVox(startPoint[np.newaxis,:], rasToIjkMatrix)
            endPointIJK = self.worldToVox(endPoint[np.newaxis,:], rasToIjkMatrix)
            
            #if i==1000:
              #print(f'linestart = {startPointIJK}')
              #print(f'lineend = {endPointIJK}')

            lumenProfile = self.lineProfile(isotropicInputVolumeArrayIJK[:,:,:],
                                            startPointIJK.flatten(),
                                            endPointIJK.flatten(),
                                            spacing=0.1,
                                            order=0)
            meanOverProfile[i] = np.nanmean(lumenProfile)
            maxOverProfile[i] = np.max(lumenProfile, initial=0)

            #update progress bar
            progressbar.value = ((i+1)/nPoints)*100
        
       
        # append to the surface model
            if scalarPrefix:
                prefix = f'{scalarPrefix}_'
            else:
                prefix = ""
        surfaceWrapper = dsa.WrapDataObject(inputModel.GetPolyData())
        surfaceWrapper.PointData.append(meanOverProfile, f'{prefix}profileMean')
        surfaceWrapper.PointData.append(maxOverProfile, f'{prefix}profileMax')
        # set to model
        outputModel.SetAndObserveMesh(surfaceWrapper.VTKObject)  
        return

    def worldToVox(self,points, affine):
        # numpy array [N,3] of floats -> numpy array [N,3] of integers
        # convert array of world coordinates (in units as mm, m etc) to voxel coordinates (in integer voxels)
        # using the affine transformation matrix
    
        appendedCoordsArray = np.ones((points.shape[0],points.shape[1]+1))
        appendedCoordsArray[:,:-1] = points
        appendedCoordsArray = np.transpose(appendedCoordsArray)
        #affineInverse = np.linalg.inv(affine)
        coordsTranspose = affine.dot(appendedCoordsArray)

        coordsTranspose = np.transpose(coordsTranspose[:-1,:])
    
        # convert to integer
        coordsTransposeInt = np.round(coordsTranspose).astype(int)
        return coordsTransposeInt

    def resampleVolumeToIsotropicSpacing(self, inputVolume, spacing):

        # Resample the volume to 0.25mm spacing
        #parameters = {"outputPixelSpacing":, "InputVolume":VolumeNode,"interpolationType":'linear',"OutputVolume":VolumeNode}
        #slicer.cli.run(slicer.modules.resamplescalarvolume, None, parameters)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode','isotropicInputVolume')

        # Set parameters
        parameters = {}
        parameters["InputVolume"] = inputVolume
        parameters["OutputVolume"] = outputVolume
        parameters["outputPixelSpacing"] = f"{spacing},{spacing},{spacing}"
        parameters["interpolationType"] = 'linear'
        # resample module
        resampler = slicer.modules.resamplescalarvolume
        cliNode = slicer.cli.runSync(resampler, None, parameters)
        # Process results
        if cliNode.GetStatus() & cliNode.ErrorsMask:
            # error
            errorText = cliNode.GetErrorText()
            slicer.mrmlScene.RemoveNode(cliNode)
            raise ValueError("CLI execution failed: " + errorText)
        # success
        slicer.mrmlScene.RemoveNode(cliNode)
        return outputVolume

    def lineProfile(self, imageArrayIJK, startCoords, endCoords, spacing=1, order=0, endPoint=True):
        # https://stackoverflow.com/questions/55651307/how-to-extract-line-profile-ray-trace-line-through-3d-matrix-ndarray-3-dim-b
        
        
        #print(imageArrayIJK.shape)
        coords = []
        n_points = int(np.ceil(spatial.distance.euclidean(startCoords, endCoords)/ spacing))
        for s, e in zip(startCoords, endCoords):
            coords.append(np.linspace(s, e, n_points, endpoint=endPoint))
        profile = ndi.map_coordinates(imageArrayIJK, coords, order=order)
        return profile  

#
# InspectVolumeWithModelTest
#

class InspectVolumeWithModelTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_InspectVolumeWithModel1()

    def test_InspectVolumeWithModel1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        #import SampleData
        #registerSampleData()
        #inputVolume = SampleData.downloadSample('InspectVolumeWithModel1')
        #self.delayDisplay('Loaded test data set')

        #inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        #self.assertEqual(inputScalarRange[0], 0)
        #self.assertEqual(inputScalarRange[1], 695)

        #outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        #threshold = 100

        # Test the module logic

        #logic = InspectVolumeWithModelLogic()

        # Test algorithm with non-inverted threshold
        #logic.process(inputVolume, outputVolume, threshold, True)
        #outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        #self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        #self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        #logic.process(inputVolume, outputVolume, threshold, False)
        #outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        #self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        #self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay('Test passed')
