import os
import unittest
import logging
import vtk, qt, ctk, slicer
import math
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# ClipBranches
#

class ClipBranches(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "ClipBranches"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Examples"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["Suze-Anne Korteland (Erasmus MC)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This module clips the branches of a vessel model
See more information in <a href="https://github.com/organization/projectname#ClipBranches">module documentation</a>.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Suze-Anne Korteland, Erasmus MC, Rotterdam.
"""

    # Additional initialization step after application startup is complete
    #slicer.app.connect("startupCompleted()", registerSampleData)

#
# Register sample data sets in Sample Data module
#


class ClipBranchesWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/ClipBranches.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = ClipBranchesLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputcenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputBranchModelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputBranchIdListSelector.connect("currentNodeChanged(vtkMRMLNode*)",self.updateParameterNodeFromGUI)
    
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
    if not self._parameterNode.GetNodeReference("firstModelNode"):
      firstModelNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLModelNode")
      if firstModelNode:
        self._parameterNode.SetNodeReferenceID("firstModelNode", firstModelNode.GetID())

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
    self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputModel"))
    self.ui.inputcenterlineSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCenterlineModel"))
    self.ui.outputBranchModelSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputBranchModel"))
    self.ui.outputBranchIdListSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputBranchIdList"))
    
    # if user has selected a centerline model, compute the branches and display them in the 3D window
    if self._parameterNode.GetNodeReference("InputCenterlineModel"):
      centerlinePolyData = self.logic.polyDataFromNode(self._parameterNode.GetNodeReference("InputCenterlineModel"))
      branchedCenterlinePolyData = self.logic.computeCenterlineBranches(centerlinePolyData)
     
      branchIdListNode = self._parameterNode.GetNodeReference("OutputBranchIdList")
      if branchIdListNode and branchIdListNode.IsA("vtkMRMLMarkupsFiducialNode"):
        # clear list and fill it again
        branchIdListNode.RemoveAllMarkups()
        branchids = []
        # get the branches out
        for i in range(branchedCenterlinePolyData.GetNumberOfCells()):
          (group_id, loc) = self.logic.getCenterlineGroup(branchedCenterlinePolyData,i)
          # display group id in 3D view
          # create markups fiducial
          if group_id not in branchids:
            # only add the group id if it is not already in the list
            n=branchIdListNode.AddFiducial(loc[0],loc[1],loc[2])
            branchIdListNode.SetNthControlPointLabel(n,str(group_id))
            branchids.append(group_id)
        
        # now create checkboxes so the user can select which branches to clip:
        ncols = 6
        nrows = math.ceil(len(branchids)/ncols)
        self.branchIdCheckBoxDict={}
        
        for i in branchids:
          newCheckBox =ctk.ctkCheckBox()
          newCheckBox.text=str(branchids[i])
          self.branchIdCheckBoxDict[branchids[i]] = newCheckBox
          row = i//ncols+1
          col = i%ncols 
          self.ui.gridLayout.addWidget(newCheckBox,row,col)
        
      
    
    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("InputModel") and self._parameterNode.GetNodeReference("InputCenterlineModel") and self._parameterNode.GetNodeReference("OutputBranchModel") and self._parameterNode.GetNodeReference("OutputBranchIdList"):
      self.ui.applyButton.toolTip = "Compute clipped model"
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = "Select input and output nodes"
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

    self._parameterNode.SetNodeReferenceID("InputModel", self.ui.inputSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputCenterlineModel", self.ui.inputcenterlineSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputBranchModel", self.ui.outputBranchModelSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputBranchIdList", self.ui.outputBranchIdListSelector.currentNodeID)
    
    self._parameterNode.EndModify(wasModified)

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    try:
      # Clip branches
      inputSurfacePolyData = self.logic.polyDataFromNode(self._parameterNode.GetNodeReference("InputModel"))
      centerlinePolyData = self.logic.polyDataFromNode(self._parameterNode.GetNodeReference("InputCenterlineModel"))
      
      # retreive the list of branch ids to be clipped
      branchClipList = []
      for key in self.branchIdCheckBoxDict:
        cb = self.branchIdCheckBoxDict[key]
        if cb.checked:
          branchClipList.append(key)
        
      outputSurfacePolyData = self.logic.clipBranches(inputSurfacePolyData,centerlinePolyData,self.ui.outputBranchModelSelector.currentNode(), branchClipList)
       
      inputSurfaceModelNode = self._parameterNode.GetNodeReference("InputModel")
      outputBranchModelNode = self._parameterNode.GetNodeReference("OutputBranchModel")
      outputBranchIdListNode = self._parameterNode.GetNodeReference("OutputBranchIdList")
      if outputBranchModelNode:
                outputBranchModelNode.SetAndObserveMesh(outputSurfacePolyData)
                if not outputBranchModelNode.GetDisplayNode():
                    outputBranchModelNode.CreateDefaultDisplayNodes()
                    outputBranchModelNode.GetDisplayNode().SetColor(0.0, 1.0, 0.0)
                    inputSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)
    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()


#
# ClipBranchesLogic
#

class ClipBranchesLogic(ScriptedLoadableModuleLogic):
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
    self.blankingArrayName = 'Blanking'
    self.radiusArrayName = 'Radius'  # maximum inscribed sphere radius
    self.groupIdsArrayName = 'GroupIds'
    self.centerlineIdsArrayName = 'CenterlineIds'
    self.tractIdsArrayName = 'TractIds'
    
  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    
  def polyDataFromNode(self, surfaceNode):
    if not surfaceNode:
      logging.error("Invalid input surface node")
      return None
      
    if surfaceNode.IsA("vtkMRMLModelNode"):
        return surfaceNode.GetPolyData()
    else:
        logging.error("Surface can only be loaded from model or segmentation node")
        return None
        
  def getCenterlineGroup(self,centerlinePolyData,idx):
    groupid = centerlinePolyData.GetCellData().GetArray('GroupIds').GetValue(idx)
    line = centerlinePolyData.GetCell(idx)
    pts = line.GetPoints()
    pt = pts.GetPoint(line.GetNumberOfPoints()//2)
    return (groupid, pt)
        
  
  def computeCenterlineBranches(self,centerlinePolyData):
    """
    Compute the centerline branches
    Can be used without the GUI widget.
    :param centerlinePolyData: Centerline model of vessel
    """
    if not centerlinePolyData:
      raise ValueError("Centerline model is invalid")
    
    try:
      import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
      
    except ImportError:
        raise ImportError("VMTK library is not found")
    
    branchExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchExtractor()
    branchExtractor.SetInputData(centerlinePolyData)
    branchExtractor.SetBlankingArrayName(self.blankingArrayName)
    branchExtractor.SetRadiusArrayName(self.radiusArrayName)
    branchExtractor.SetGroupIdsArrayName(self.groupIdsArrayName)
    branchExtractor.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
    branchExtractor.SetTractIdsArrayName(self.tractIdsArrayName)
    branchExtractor.Update()
    centerlines = branchExtractor.GetOutput()
    return centerlines
    
  def clipBranches(self, surfacePolyData, centerlinePolyData, outputModel, branchClipList, showResult=True):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param surfacePolyData: Vascular model from which the branches should be clipped
    :param centerlinePolyData: Centerline model of vessel with branches on which to base the clipping
    :param outputModel: resulting model with branches removed
    :param showResult: show output model in slice viewers
    """

    if not surfacePolyData or not centerlinePolyData or not outputModel:
      raise ValueError("Input or output model is invalid")

    import time
    startTime = time.time()
    logging.info('Processing started')

    # Compute the model with the sidebranches removed using the slicervmtk module
    
    try:
      import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
      
    except ImportError:
        raise ImportError("VMTK library is not found")
    
    branchExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchExtractor()
    branchExtractor.SetInputData(centerlinePolyData)
    branchExtractor.SetBlankingArrayName(self.blankingArrayName)
    branchExtractor.SetRadiusArrayName(self.radiusArrayName)
    branchExtractor.SetGroupIdsArrayName(self.groupIdsArrayName)
    branchExtractor.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
    branchExtractor.SetTractIdsArrayName(self.tractIdsArrayName)
    branchExtractor.Update()
    centerlines = branchExtractor.GetOutput()
    
    # there seems to be a bug in vtkvmtkPolyDatacenterlineGroupsClipper where you can only clip one branch at a time, when you try to clip multiple branches at once, nothing happens. THerefore clip the branches one by one in a loop.
    surface = surfacePolyData
    for i in branchClipList:
      surfaceClipper = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlineGroupsClipper()
      surfaceClipper.SetInputData(surface)
      surfaceClipper.SetCenterlines(centerlines)
      surfaceClipper.SetCenterlineGroupIdsArrayName(self.groupIdsArrayName)
      surfaceClipper.SetGroupIdsArrayName(self.groupIdsArrayName)
      surfaceClipper.SetCenterlineRadiusArrayName(self.radiusArrayName)
      surfaceClipper.SetBlankingArrayName(self.blankingArrayName)
      surfaceClipper.SetGenerateClippedOutput(1)
      groupIds = vtk.vtkIdList()
      groupIds.InsertNextId(i)
      surfaceClipper.SetCenterlineGroupIds(groupIds)
      surfaceClipper.SetClipAllCenterlineGroupIds(0)
      #surfaceClipper.GenerateClippedOutputOff()
      # clip all branches
      #surfaceClipper.SetClipAllCenterlineGroupIds(1)
      surfaceClipper.Update()
      
      surface = surfaceClipper.GetClippedOutput()
    

    outputSurfacePolyData = vtk.vtkPolyData()
    outputSurfacePolyData.DeepCopy(surfaceClipper.GetClippedOutput())
    
    stopTime = time.time()
    logging.info('Processing completed in {0:.2f} seconds'.format(stopTime-startTime))
    
    return outputSurfacePolyData
#
# ClipBranchesTest
#

class ClipBranchesTest(ScriptedLoadableModuleTest):
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
    self.test_ClipBranches1()

  def test_ClipBranches1(self):
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

    # self.delayDisplay("Starting the test")

    # # Get/create input data

    # import SampleData
    # registerSampleData()
    # inputVolume = SampleData.downloadSample('ClipBranches1')
    # self.delayDisplay('Loaded test data set')

    # inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    # self.assertEqual(inputScalarRange[0], 0)
    # self.assertEqual(inputScalarRange[1], 695)

    # outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    # threshold = 100

    # # Test the module logic

    # logic = ClipBranchesLogic()

    # # Test algorithm with non-inverted threshold
    # logic.process(inputVolume, outputVolume, threshold, True)
    # outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    # self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    # self.assertEqual(outputScalarRange[1], threshold)

    # # Test algorithm with inverted threshold
    # logic.process(inputVolume, outputVolume, threshold, False)
    # outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    # self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    # self.assertEqual(outputScalarRange[1], inputScalarRange[1])

    # self.delayDisplay('Test passed')
