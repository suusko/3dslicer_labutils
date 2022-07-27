import logging
import os

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# OpenSurface
#

class OpenSurface(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "OpenSurface"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Examples"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["Suze-Anne korteland (Erasmus MC)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This module can be used to open a vessel surface normal to a centerline curve.
See more information in <a href="https://github.com/organization/projectname#OpenSurface">module documentation</a>.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed Suze-anne korteland, Erasmus MC, Rotterdam.
"""


#
# OpenSurfaceWidget
#

class OpenSurfaceWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/OpenSurface.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    self.nodeSelectors = [
    (self.ui.inputSurfaceSelector, "InputSurface"),
    (self.ui.inputCenterlineSelector, "InputCenterline"),
    (self.ui.outputSurfaceSelector, "OutputSurface")
    ]

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = OpenSurfaceLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputSurfaceSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputCenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputSurfaceSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
   
    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.showPlaneButton.connect('clicked(bool)', self.onShowPlaneButton)
    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

    # Select default input nodes if nothing is selected yet to save a few clicks for the user
    if not self._parameterNode.GetNodeReference("InputSurface"):
      firstModelNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLModelNode")
      if firstModelNode:
        self._parameterNode.SetNodeReferenceID("InputSurface", firstModelNode.GetID())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    # Update node selectors and sliders
    for nodeSelector,roleName in self.nodeSelectors:
      nodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(roleName))
      
    # Update buttons states and tooltips
    
    if self._parameterNode.GetNodeReference("InputSurface") and self._parameterNode.GetNodeReference("InputCenterline"):
      self.ui.showPlaneButton.toolTip = "Compute clipping plane"
      self.ui.showPlaneButton.enabled = True
    else:
      self.ui.showPlaneButton.toolTip = "Select input surface and centerline nodes"
      self.ui.showPlaneButton.enabled = False

    clipReady = False
    if clipReady:
      self.ui.applyButton.toolTip = "Clip surface with plane" 
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = " to apply clip, first compute clipping plane"
      self.ui.applyButton.enabled = False
      
    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch
    
    for nodeSelector, roleName in self.nodeSelectors:
      self._parameterNode.SetNodeReferenceID(roleName, nodeSelector.currentNodeID)
   

    self._parameterNode.EndModify(wasModified)


  def onShowPlaneButton(self):
    """
    Run processing when user clicks "showPlane" button.
    """
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
      # retreive the centerline curve data
      inputCenterlinePolyData = self.logic.polyDataFromNode(self._parameterNode.GetNodeReference("InputCenterline"))
      
      # compute centerline normals and tangents
      self.centerlineGeometryPolyData = self.logic.computeCenterlineGeometry(inputCenterlinePolyData)
      
      # Todo: move this to logic class
      from vtk.numpy_interface import dataset_adapter as dsa

      pointdata = dsa.WrapDataObject(self.centerlineGeometryPolyData).PointData
      normaldata = pointdata['FrenetNormal']
      tangentdata = pointdata['FrenetTangent']
      points = dsa.WrapDataObject(self.centerlineGeometryPolyData).Points

      # create a plane normal to the centerline curve at the end location
      planeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsPlaneNode')
      planeNode.SetCenter(points[0,:])
      planeNode.SetNormal(tangentdata[0,:]) 
      # display the plane in the ui
      
      
      # Todo: let the user select the location of the plane along the centerline curve either by mouseclick or through a slider
    
    
  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

      # Compute output
      self.logic.process(self.ui.inputSelector.currentNode(), self.ui.outputSelector.currentNode(),
        self.ui.imageThresholdSliderWidget.value, self.ui.invertOutputCheckBox.checked)

      # Compute inverted output (if needed)
      if self.ui.invertedOutputSelector.currentNode():
        # If additional output volume is selected then result with inverted threshold is written there
        self.logic.process(self.ui.inputSelector.currentNode(), self.ui.invertedOutputSelector.currentNode(),
          self.ui.imageThresholdSliderWidget.value, not self.ui.invertOutputCheckBox.checked, showResult=False)


#
# OpenSurfaceLogic
#

class OpenSurfaceLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.lengthArrayName = 'Length'
    self.curvatureArrayName = 'Curvature'
    self.torsionArrayName = 'Torsion'
    self.tortuosityArrayName = 'Tortuosity'
    self.frenetTangentArrayName = 'FrenetTangent'
    self.frenetNormalArrayName = 'FrenetNormal'
    self.frenetBinormalArrayName = 'FrenetBinormal'
    

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("Threshold"):
      parameterNode.SetParameter("Threshold", "100.0")
    if not parameterNode.GetParameter("Invert"):
      parameterNode.SetParameter("Invert", "false")

  def polyDataFromNode(self, surfaceNode):
    if not surfaceNode:
      logging.error("Invalid input surface node")
      return None
    
    if surfaceNode.IsA("vtkMRMLModelNode"):
      return surfaceNode.GetPolyData()
    else:
      logging.error("Surface can only be loaded from model or segmentation node")
      return None
      
  def computeCenterlineGeometry(self,centerlinePolyData):
    """
    Compute the centerline geometry
    Can be used without the GUI widget.
    :param centerlinePolyData: Centerline model of vessel
    """
    import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
    centerlineGeometry = vtkvmtkComputationalGeometry.vtkvmtkCenterlineGeometry()
    centerlineGeometry.SetInputData(centerlinePolyData)
    centerlineGeometry.SetLengthArrayName(self.lengthArrayName)
    centerlineGeometry.SetCurvatureArrayName(self.curvatureArrayName)
    centerlineGeometry.SetTorsionArrayName(self.torsionArrayName)
    centerlineGeometry.SetTortuosityArrayName(self.tortuosityArrayName)
    centerlineGeometry.SetFrenetTangentArrayName(self.frenetTangentArrayName)
    centerlineGeometry.SetFrenetNormalArrayName(self.frenetNormalArrayName)
    centerlineGeometry.SetFrenetBinormalArrayName(self.frenetBinormalArrayName)
    # centerlineGeometry.SetLineSmoothing(0)
    # centerlineGeometry.SetOutputSmoothedLines(0)
    # centerlineGeometry.SetNumberOfSmoothingIterations(100)
    # centerlineGeometry.SetSmoothingFactor(0.1)
    centerlineGeometry.Update()
    return centerlineGeometry.GetOutput()
    
      
  def process(self, inputVolume, outputVolume, imageThreshold, invert=False, showResult=True):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputVolume: volume to be thresholded
    :param outputVolume: thresholding result
    :param imageThreshold: values above/below this threshold will be set to 0
    :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
    :param showResult: show output volume in slice viewers
    """

    if not inputVolume or not outputVolume:
      raise ValueError("Input or output volume is invalid")

    import time
    startTime = time.time()
    logging.info('Processing started')

    # Compute the thresholded output volume using the "Threshold Scalar Volume" CLI module
    cliParams = {
      'InputVolume': inputVolume.GetID(),
      'OutputVolume': outputVolume.GetID(),
      'ThresholdValue' : imageThreshold,
      'ThresholdType' : 'Above' if invert else 'Below'
      }
    cliNode = slicer.cli.run(slicer.modules.thresholdscalarvolume, None, cliParams, wait_for_completion=True, update_display=showResult)
    # We don't need the CLI module node anymore, remove it to not clutter the scene with it
    slicer.mrmlScene.RemoveNode(cliNode)

    stopTime = time.time()
    logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')


#
# OpenSurfaceTest
#

class OpenSurfaceTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_OpenSurface1()

  def test_OpenSurface1(self):
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

    import SampleData
    registerSampleData()
    inputVolume = SampleData.downloadSample('OpenSurface1')
    self.delayDisplay('Loaded test data set')

    inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    self.assertEqual(inputScalarRange[0], 0)
    self.assertEqual(inputScalarRange[1], 695)

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    threshold = 100

    # Test the module logic

    logic = OpenSurfaceLogic()

    # Test algorithm with non-inverted threshold
    logic.process(inputVolume, outputVolume, threshold, True)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], threshold)

    # Test algorithm with inverted threshold
    logic.process(inputVolume, outputVolume, threshold, False)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], inputScalarRange[1])

    self.delayDisplay('Test passed')
