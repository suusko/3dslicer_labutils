import logging
import os
import math
import vtk
import ctk
import qt
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# AddFlowExtension
#

class AddFlowExtension(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "AddFlowExtension"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Examples"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["Suze-Anne Korteland (Erasmus MC)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This module can be used to add flow extensions to a surface model for use in CFD
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Suze-Anne Korteland, department of Biomedical Engineering, Erasmus MC, Rotterdam
"""

#
# AddFlowExtensionWidget
#

class AddFlowExtensionWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/AddFlowExtension.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = AddFlowExtensionLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputSurfaceSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputCenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputSurfaceSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.extensionLengthSpinBox.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    self.ui.selectOpenBoundariesCheckBox.connect("stateChanged(int)",self.onSelectOpenBoundariesStateChanged)
    self.ui.addCapsCheckBox.connect("stateChanged(int)",self.updateParameterNodeFromGUI)
    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

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
      firstSurfaceNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLModelNode")
      if firstSurfaceNode:
        self._parameterNode.SetNodeReferenceID("InputSurface", firstSurfaceNode.GetID())

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
    self.ui.inputSurfaceSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputSurface"))
    self.ui.inputCenterlineSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCenterline"))
    self.ui.outputSurfaceSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputSurface"))
    self.ui.extensionLengthSpinBox.value = float(self._parameterNode.GetParameter("ExtensionLength"))
    
    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("InputSurface") and self._parameterNode.GetNodeReference("InputCenterline") and self._parameterNode.GetNodeReference("OutputSurface"):
      self.ui.applyButton.toolTip = "Add flow extensions"
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = "Select input and output model nodes"
      self.ui.applyButton.enabled = False

    # do not block signals so that related widgets are enabled/disabled according to its state
    self.ui.selectOpenBoundariesCheckBox.checked = (self._parameterNode.GetParameter("SelectOpenBoundaries") == "true")

    self.ui.addCapsCheckBox.checked = (self._parameterNode.GetParameter("AddCaps") == "true")


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

    self._parameterNode.SetNodeReferenceID("InputSurface", self.ui.inputSurfaceSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputCenterline", self.ui.inputCenterlineSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputSurface", self.ui.outputSurfaceSelector.currentNodeID)
    self._parameterNode.SetParameter("ExtensionLength",str(self.ui.extensionLengthSpinBox.value))
    self._parameterNode.SetParameter("AddCaps", "true" if self.ui.addCapsCheckBox.checked else "false")
    self._parameterNode.EndModify(wasModified)
    
  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

      # Compute output
      inputSurfacePolyData = self.logic.polyDataFromNode(self.ui.inputSurfaceSelector.currentNode())
      inputCenterlinePolyData = self.logic.polyDataFromNode(self.ui.inputCenterlineSelector.currentNode())
      
      selectOpenBoundaries = (self._parameterNode.GetParameter("SelectOpenBoundaries") == "true")
      openBoundsIdList = None
      if selectOpenBoundaries:
        # get the ids of the open boundaries to extend
        openBoundsIdList = []
        for key in self.openBoundariesCheckBoxDict:
          cb = self.openBoundariesCheckBoxDict[key]
          if cb.checked:
            openBoundsIdList.append(key)
       
      extensionLength = float(self._parameterNode.GetParameter("ExtensionLength"))
      
      outputSurfacePolyData = self.logic.addFlowExtensions(inputSurfacePolyData, inputCenterlinePolyData, openBoundsIdList,extensionLength)
      
      
    
    addCaps = (self._parameterNode.GetParameter("AddCaps") == "true")
    if addCaps:
      outputSurfacePolyData = self.logic.addCaps(outputSurfacePolyData)
      
    outputSurfaceNode = self._parameterNode.GetNodeReference("OutputSurface")
    if outputSurfaceNode:
      outputSurfaceNode.SetAndObserveMesh(outputSurfacePolyData)  

  # this function is called when checkbox "select open boundaries"  changes state
  def onSelectOpenBoundariesStateChanged(self):
    
    self._parameterNode.SetParameter("SelectOpenBoundaries", "true" if self.ui.selectOpenBoundariesCheckBox.checked else "false")
    
    selectOpenBoundaries = self.ui.selectOpenBoundariesCheckBox.isChecked()
    if selectOpenBoundaries:
      # show the id's of the open boundaries to which flow extensions can be added
      # compute locations of the open boundaries
      inputSurfacePolyData = self.logic.polyDataFromNode(self.ui.inputSurfaceSelector.currentNode())
      
      # get the barycenters of the open boundaries
      barycenterPolyData = self.logic.getOpenBoundariesBarycenters(inputSurfacePolyData)
      
      # creat/ get reference to markup node to display the boundary ids at the barycenters
      openBoundariesIdsMarkupsNode = self._parameterNode.GetNodeReference("OpenBoundariesIds")
      if not openBoundariesIdsMarkupsNode:
        openBoundariesIdsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode","OpenBoundariesIds")
        if openBoundariesIdsMarkupsNode:
          self._parameterNode.SetNodeReferenceID("OpenBoundariesIds",openBoundariesIdsMarkupsNode.GetID())
      else:
        # the node already exists, so empty it to fill it with the current barycenters 
        # empty the node
        openBoundariesIdsMarkupsNode.RemoveAllMarkups()
        
      # add markups corresonding to the barycenters of the open boundaries with the boundary id as label
      openbounds_ids = []
      for i in range(barycenterPolyData.GetNumberOfPoints()):
        point = barycenterPolyData.GetPoint(i)
        
        n = openBoundariesIdsMarkupsNode.AddFiducial(point[0],point[1],point[2])
        openBoundariesIdsMarkupsNode.SetNthControlPointLabel(n,str(i))
        openbounds_ids.append(i)
        
      # now create checkboxes so the user can select which open boundaries to extend
      hlayout = qt.QHBoxLayout() # horizontal layout to hold the checkboxes
      self.openBoundariesCheckBoxDict={}
      for (i,id) in enumerate(openbounds_ids):
        newCheckBox = ctk.ctkCheckBox()
        newCheckBox.text=str(id)
        self.openBoundariesCheckBoxDict[id] = newCheckBox
        hlayout.addWidget(newCheckBox) # add checkbox widget to layout
        
      # add layout with checkboxes to parent layout       
      self.ui.formLayout.addRow("id:",hlayout)
    else:
      # remove the open boundaries markupsnode and related variables, if it exists
      openBoundariesIdsMarkupsNode = self._parameterNode.GetNodeReference("OpenBoundariesIds")
      if openBoundariesIdsMarkupsNode:
        self.openBoundariesCheckBoxDict={}
        idx = self.ui.formLayout.rowCount()
        self.ui.formLayout.removeRow(idx-1)
        slicer.mrmlScene.RemoveNode(openBoundariesIdsMarkupsNode)
      
    
#
# AddFlowExtensionLogic
#

class AddFlowExtensionLogic(ScriptedLoadableModuleLogic):
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

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("ExtensionLength"):
      parameterNode.SetParameter("ExtensionLength","5.0")
    if not parameterNode.GetParameter("SelectOpenBoundaries"):
      parameterNode.SetParameter("SelectOpenBoundaries", "true")
    if not parameterNode.GetParameter("AddCaps"):
      parameterNode.SetParameter("AddCaps", "false")
    return
  
  def polyDataFromNode(self, surfaceNode):
    if not surfaceNode:
      logging.error("Invalid input surface node")
      return None
    if surfaceNode.IsA("vtkMRMLModelNode"):
      return surfaceNode.GetPolyData()
    else:
      logging.error("Surface can only be loaded from model node")
      return None
    
  def getOpenBoundariesBarycenters(self, surfacePolyData):
    """ compute the barycenters of the open boundaries of a surface """
    # based on code in https://github.com/vmtk/vmtk/blob/master/vmtkScripts/vmtkflowextensions.py
    import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
    
    
    boundaryExtractor = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryExtractor()
    boundaryExtractor.SetInputData(surfacePolyData)
    boundaryExtractor.Update()
    boundaries = boundaryExtractor.GetOutput()
    numberOfBoundaries = boundaries.GetNumberOfCells()
    
    seedPoints = vtk.vtkPoints()
   
    for i in range(numberOfBoundaries):
      barycenter = [0.0, 0.0, 0.0]
      vtkvmtkComputationalGeometry.vtkvmtkBoundaryReferenceSystems.ComputeBoundaryBarycenter(boundaries.GetCell(i).GetPoints(),barycenter)
      seedPoints.InsertNextPoint(barycenter)
      
    seedPolyData = vtk.vtkPolyData()
    seedPolyData.SetPoints(seedPoints)
    
    return seedPolyData
    
  def addFlowExtensions(self, inputSurfacePolyData, inputCenterlinePolyData, boundaryIds=None,extensionLength=None):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputSurfacePolyData: Polydata surface to which flow extensions should be added
    :param inputCenterlinePolyData: Polydata centerline to use for the direction of the flow extensions
    """
    import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
   
    if not inputSurfacePolyData or not inputCenterlinePolyData:
      raise ValueError("Input Surface, input Centerline, or output surface is invalid")

    # TODO: let the user set the flowextension filter properties in the advanced tab in the GUI
    flowExtensionsFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataFlowExtensionsFilter()
    flowExtensionsFilter.SetInputData(inputSurfacePolyData)
    flowExtensionsFilter.SetCenterlines(inputCenterlinePolyData)
    flowExtensionsFilter.SetSigma(1) # default value, thin plate spline stiffness
    flowExtensionsFilter.SetAdaptiveExtensionLength(1) # bool, set extension length proportional to mean flow radius
    flowExtensionsFilter.SetAdaptiveExtensionRadius(1) # bool
    flowExtensionsFilter.SetAdaptiveNumberOfBoundaryPoints(0) # bool,default value
    flowExtensionsFilter.SetExtensionLength(1) # default value 
    if extensionLength:
      flowExtensionsFilter.SetExtensionRatio(extensionLength) # proportionality factor, how much is the extension length extended 
    flowExtensionsFilter.SetExtensionRadius(1) # float, ?
    flowExtensionsFilter.SetTransitionRatio(0.25) # default value, ratio with which the extension changes to circular boundary
    flowExtensionsFilter.SetCenterlineNormalEstimationDistanceRatio(1.0) #default value, controls how far into the centerline the algorithm looks for computing the orientation of the flow extension.
    #flowExtensionsFilter.SetNumberOfBoundaryPoints(self.TargetNumberOfBoundaryPoints)
    # use centerline for extension direction
    flowExtensionsFilter.SetExtensionModeToUseCenterlineDirection()
    # set the boundaries that should be extended
    if boundaryIds:
      boundaryIdsList = vtk.vtkIdList()
      for i in boundaryIds:
        boundaryIdsList.InsertNextId(i)
      flowExtensionsFilter.SetBoundaryIds(boundaryIdsList)
    flowExtensionsFilter.Update()
    
    return flowExtensionsFilter.GetOutput()
  
  def addCaps(self, surfacePolyData):
    import vtkvmtkMiscPython as vtkvmtkMisc
    
    if not surfacePolyData:
      raise ValueError("Input Surface is invalid")
      
    addCapsFilter = vtkvmtkMisc.vtkvmtkSimpleCapPolyData()
    addCapsFilter.SetInputData(surfacePolyData)
    addCapsFilter.Update()
    
    return addCapsFilter.GetOutput()
    
#
# AddFlowExtensionTest
#

class AddFlowExtensionTest(ScriptedLoadableModuleTest):
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
    self.test_AddFlowExtension1()

  def test_AddFlowExtension1(self):
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
    inputVolume = SampleData.downloadSample('AddFlowExtension1')
    self.delayDisplay('Loaded test data set')

    inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    self.assertEqual(inputScalarRange[0], 0)
    self.assertEqual(inputScalarRange[1], 695)

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    threshold = 100

    # Test the module logic

    logic = AddFlowExtensionLogic()

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
