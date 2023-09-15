import logging
import os

import vtk
import qt
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# PrepareModelForCFD
#

class PrepareModelForCFD(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "PrepareModelForCFD"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["LabUtils"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["S. Korteland (Erasmus MC)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This is a slicelet module to simplify the workflow for the preparation of a geometry for CFD meshing (load model, compute centerlines, open model, add flow extensions)
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by S. Korteland, Department of Biomedical Engineering, Erasmus MC, Rotterdam.
"""

#
# PrepareModelForCFDWidget
#

class PrepareModelForCFDWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = PrepareModelForCFDLogic()
    
    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/PrepareModelForCFD.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    
    uiWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.SubjectHierarchyTreeView.setMRMLScene(slicer.mrmlScene)  
    # Buttons
    self.ui.loadButton.connect('clicked(bool)', self.onLoadButton)
    self.ui.endPointMarkupsSelector.connect("currentNodeChanged(vtkMLMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.autoDetectEndPointsPushButton.connect('clicked(bool)',self.onAutoDetectEndPointsButton)
    self.ui.computeCenterlineButton.connect('clicked(bool)', self.onComputeCenterlineButton)
    self.ui.openModelButton.connect('clicked(bool)', self.onOpenModelButton)
    self.ui.addFlowExtensionsButton.connect('clicked(bool)', self.onAddFlowExtensionsButton)
    self.ui.exportModelButton.connect('clicked(bool)', self.onExportModelButton)
    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).

    # set layout to 3D view only
    layoutManager = slicer.app.layoutManager()
    layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
   

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

    self.isSingleModuleShown = False
    slicer.util.mainWindow().setWindowTitle("Prepare Model for CFD")
    self.showSingleModule(True)
    shortcut = qt.QShortcut(slicer.util.mainWindow())
    shortcut.setKey(qt.QKeySequence("Ctrl+Shift+b"))
    shortcut.connect('activated()', lambda: self.showSingleModule(toggle=True))


   

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

    # Update node selectors and slider
    self.ui.endPointMarkupsSelector.setCurrentNode(self._parameterNode.GetNodeReference("EndPoints"))

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    self._parameterNode.SetNodeReferenceID("EndPoints", self.ui.endPointsMarkupsSelector.currentNodeID)

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    

    self._parameterNode.EndModify(wasModified)

  def onLoadButton(self):
    """ load model """
    print("load model")   
    with slicer.util.tryWithErrorDisplay("Failed to load file", waitCursor=True):

      filePath = self.ui.filePathLineEdit.currentPath
      # try loading file using slicer data loader
      surfaceNode = slicer.util.loadModel(filePath) 

      # set visibility
      surfaceNode.GetDisplayNode().SetVisibility(1) 
      
      # Center view
      threeDView=slicer.app.layoutManager().threeDWidget(0).threeDView()
      # center 3Dview on the scene
      threeDView.resetFocalPoint()
      # hide bounding box
      viewNode = slicer.app.layoutManager().threeDWidget(0).mrmlViewNode()
      viewNode.SetBoxVisible(0)
      viewNode.SetAxisLabelsVisible(0)
      # display orientation marker
      viewNode.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)

      # save to parameter node
      self._parameterNode.SetNodeReferenceID("SurfaceModel",surfaceNode.GetID())

      # open the next step
      self.ui.computeCenterlineCollapsibleButton.collapsed = False
      self.ui.loadCollapsibleButton.collapsed = True
 
  def getPreprocessedPolyData(self, surfaceModelNode):
    """ Preprocess the surface polydata for centerline computation. Code based on ExtractCenterlineWidget and
    ExtractCenterlineLogic"""
    extractCenterlineLogic = slicer.modules.extractcenterline.widgetRepresentation().self().logic

    targetNumberOfPoints = 5000 # default
    decimationAggressiveness = 4.0 # default
    subdivideInputSurface = False # default
    preprocessedPolyData = extractCenterlineLogic.preprocess(surfaceModelNode.GetPolyData(), targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface)

    return preprocessedPolyData
  
  def onAutoDetectEndPointsButton(self):
    surfaceModelNode = self._parameterNode.GetNodeReference("SurfaceModel")
    endPointsNode = self._parameterNode.GetNodeReference("EndPoints")
    if not endPointsNode:
      endPointsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode",
            "CenterlineEndPoints")
      endPointsNode.CreateDefaultDisplayNodes()
      self._parameterNode.SetNodeReferenceID("EndPoints", endPointsNode.GetID())
      # Make input surface semi-transparent to make all detected endpoints visible
      surfaceModelNode.GetDisplayNode().SetOpacity(0.8)

      self.autoDetectEndPoints(surfaceModelNode,endPointsNode)

      # display endpoint labels
      endPointsNode.SetControlPointLabelFormat("%d")
      # update control points with current format
      slicer.modules.markups.logic().RenameAllControlPointsFromCurrentFormat(endPointsNode)
      endPointsNode.GetDisplayNode().SetPointLabelsVisibility(True)

      # create radiobuttons so the user can select which endPoint should be the inlet
      self.updateInletRadioButtons(endPointsNode)

      # when user removes or adds point to the endpointsNode, recreate the inlet radiobuttons
      endPointsNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointAddedEvent,self.updateInletRadioButtons)
      endPointsNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent,self.updateInletRadioButtons)

      # enable inlet radiobuttons groupbox
      self.ui.selectInletGroupBox.enabled = True

  def updateInletRadioButtons(self,caller,event=None):
    endPointsNode = caller
    # clear existing widgets in the layout
    layout = self.ui.selectInletGroupBox.layout()
    if layout is not None:
      # remove all children
      while layout.count():
        item=layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
          widget.deleteLater()
    else:
      #create layout
      layout = qt.QHBoxLayout()
      self.ui.selectInletGroupBox.setLayout(layout)

    self.inletRadioButtonsList=[]
    for i in range(endPointsNode.GetNumberOfControlPoints()):
      newRadioButton = qt.QRadioButton()
      newRadioButton.text=endPointsNode.GetNthControlPointLabel(i)
      self.inletRadioButtonsList.append(newRadioButton)
      # check the radiobutton if its corresponding control point is unchecked to indicate the startpoint for centerline computation
      if not endPointsNode.GetNthControlPointSelected(i):
        newRadioButton.checked = True

      #connect event handler when the button is toggled
      newRadioButton.toggled.connect(self.onInletRadioButtonToggled)
      layout.addWidget(newRadioButton) # add checkbox widget to layout
       
  def onInletRadioButtonToggled(self,checked):
    if not checked:
      return
    else:
      endPointsNode = self._parameterNode.GetNodeReference("EndPoints")
      # select all controlpoints, then deselect the one that was marked as inlet
      slicer.modules.markups.logic().SetAllControlPointsSelected(endPointsNode,True)

      # get the markupsnode controlpoint associated with the selected radio button and unselect it
      for (i,btn) in enumerate(self.inletRadioButtonsList):
        if btn.isChecked():
          endPointsNode.SetNthControlPointSelected(i,False)

  def autoDetectEndPoints(self, surfaceModelNode, endPointsNode):
    """
    Automatically detect mesh endpoints, code based on ExtractCenterlineWidget and ExtractCenterlineLogic
    """
    extractCenterlineLogic = slicer.modules.extractcenterline.widgetRepresentation().self().logic

    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    try:
      slicer.util.showStatusMessage("Preprocessing...")
      slicer.app.processEvents()  # force update
      preprocessedPolyData = self.getPreprocessedPolyData(surfaceModelNode)
      endPointsNode.RemoveAllControlPoints()

      slicer.util.showStatusMessage("Extract network...")
      slicer.app.processEvents()  # force update
      networkPolyData = extractCenterlineLogic.extractNetwork(preprocessedPolyData, endPointsNode)

      endpointPositions = extractCenterlineLogic.getEndPoints(networkPolyData, startPointPosition=None)

      endPointsNode.GetDisplayNode().PointLabelsVisibilityOff()
      for position in endpointPositions:
        endPointsNode.AddControlPoint(vtk.vtkVector3d(position))

      # Mark the first node as unselected, which means that it is the start point
      # (by default points are selected and there are more endpoints and only one start point,
      # therefore indicating start point by non-selected stat requires less clicking)
      if endPointsNode.GetNumberOfControlPoints() > 0:
        endPointsNode.SetNthControlPointSelected(0, False)

    except Exception as e:
      slicer.util.errorDisplay("Failed to detect end points: "+str(e))
      import traceback
      traceback.print_exc()
    qt.QApplication.restoreOverrideCursor()

    slicer.util.showStatusMessage("Automatic endpoint computation complete.", 3000)

  def onComputeCenterlineButton(self):
    """ compute centerline """
    # compute centerline and its attributes and metrics for next postprocessing step
    surfaceNode = self._parameterNode.GetNodeReference("SurfaceModel")
    endPointsNode = self._parameterNode.GetNodeReference("EndPoints")

    # compute centerline
    ExtractCenterlineLogic = slicer.modules.extractcenterline.widgetRepresentation().self().logic
    ClipBranchesLogic = slicer.modules.clipbranches.widgetRepresentation().self().logic

    # preprocess polydata to improve centerline computation
    preprocessedPolyData = self.getPreprocessedPolyData(surfaceNode)
    curveSamplingDistance = 1.0 # default
    centerlinePolyData, _ = ExtractCenterlineLogic.extractCenterline(preprocessedPolyData,endPointsNode,curveSamplingDistance)

    # split centerlines into branches
    centerlinePolyData = ClipBranchesLogic.computeCenterlineBranches(centerlinePolyData)

    # to node
    centerlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode",'CenterlineModel')
    centerlineModelNode.SetAndObserveMesh(centerlinePolyData)
    if not centerlineModelNode.GetDisplayNode():
      centerlineModelNode.CreateDefaultDisplayNodes()
    centerlineModelNode.GetDisplayNode().SetVisibility(1)
    centerlineModelNode.GetDisplayNode().SetLineWidth(5)
    # reduce opacity of surface model
    surfaceNode.GetDisplayNode().SetOpacity(0.4)

    # Open the next step
    self.ui.openModelCollapsibleButton.collapsed = False
    self.ui.computeCenterlineCollapsibleButton.collapsed = True

    
  def onOpenModelButton(self):
    """" open surface """
    # switch to open surface module to open the model
    slicer.util.selectModule("OpenSurface")
    
  def onAddFlowExtensionsButton(self):
    """ add flow extensions """
    slicer.util.selectModule("AddFlowExtension")
    
  def onExportModelButton(self):
    """ export models """
    slicer.util.openSaveDataDialog()    
    
  def showSingleModule(self, singleModule=True, toggle=False):

    if toggle:
      singleModule = not self.isSingleModuleShown

    self.isSingleModuleShown = singleModule

    if singleModule:
      # We hide all toolbars, etc. which is inconvenient as a default startup setting,
      # therefore disable saving of window setup.
      import qt
      settings = qt.QSettings()
      settings.setValue('MainWindow/RestoreGeometry', 'false')

      keepToolbars = [
        slicer.util.findChild(slicer.util.mainWindow(), 'MainToolBar'),
        slicer.util.findChild(slicer.util.mainWindow(), 'ModuleSelectorToolBar')]
      slicer.util.setToolbarsVisible(not singleModule, keepToolbars)
      #slicer.util.setMenuBarsVisible(not singleModule)
      slicer.util.setApplicationLogoVisible(not singleModule)
      slicer.util.setModuleHelpSectionVisible(not singleModule)
      slicer.util.setModulePanelTitleVisible(not singleModule)
      slicer.util.setDataProbeVisible(not singleModule)
      slicer.util.setViewControllersVisible(not singleModule)

      # set layout to 3D only
      layoutManager = slicer.app.layoutManager()
      layoutManager.setLayout(4)
    #if singleModule:
    #  slicer.util.setPythonConsoleVisible(False)
#
# PrepareModelForCFDLogic
#

class PrepareModelForCFDLogic(ScriptedLoadableModuleLogic):
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
    if not parameterNode.GetParameter("Threshold"):
      parameterNode.SetParameter("Threshold", "100.0")
    if not parameterNode.GetParameter("Invert"):
      parameterNode.SetParameter("Invert", "false")

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
# PrepareModelForCFDTest
#

class PrepareModelForCFDTest(ScriptedLoadableModuleTest):
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
    self.test_PrepareModelForCFD1()

  def test_PrepareModelForCFD1(self):
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
    inputVolume = SampleData.downloadSample('PrepareModelForCFD1')
    self.delayDisplay('Loaded test data set')

    inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    self.assertEqual(inputScalarRange[0], 0)
    self.assertEqual(inputScalarRange[1], 695)

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    threshold = 100

    # Test the module logic

    logic = PrepareModelForCFDLogic()

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
