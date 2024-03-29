import logging
import os

import vtk
from vtk.numpy_interface import dataset_adapter as dsa
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np

#
# OpenSurface
# TODO: Add mouse interaction for selection of the clipping ROI
# TODO: clip centerlines to match opened model

class OpenSurface(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "OpenSurface"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["LabUtils"]  # TODO: set categories (folders where the module shows up in the module selector)
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

    # initialize pointslocator, used in the positioning of the ROI box for clipping, to None 
    self.pointsLocator = None

    # intitialize indicator whether ROIbox should be moved or not
    self.moveROIBox = False

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

    # slider
    #self.ui.planeLocationWidget.connect('valueChanged(double)', self.setCurrentPlaneIndex)
    
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
    # shows the ROI box if present
    ROIBoxNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
    if ROIBoxNode:
      ROIBoxNode.SetDisplayVisibility(1)
      # add observer to move the Roibox
      crosshairNode=slicer.util.getNode("Crosshair")
      self.ROIPlacementObservationId = crosshairNode.AddObserver(slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent, self.onMouseMoved)
      # add observer for key presses
      interactor = slicer.app.layoutManager().threeDWidget(0).threeDView().interactor()
      self.keyPressObservationId = interactor.AddObserver(vtk.vtkCommand.KeyPressEvent, self.processEvent)
      # add observer for key releases
      self.keyReleaseObservationId = interactor.AddObserver(vtk.vtkCommand.KeyReleaseEvent, self.processEvent)

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    # hide the ROI box if present
    ROIBoxNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
    if ROIBoxNode:
      ROIBoxNode.SetDisplayVisibility(0)
      # remove observer
      crosshairNode=slicer.util.getNode("Crosshair")
      crosshairNode.RemoveObserver(self.ROIPlacementObservationId)
      interactor = slicer.app.layoutManager().threeDWidget(0).threeDView().interactor()
      interactor.RemoveObserver(self.keyPressObservationId)
      interactor.RemoveObserver(self.keyReleaseObservationId)

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
    print(event)
    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return
    print("In UpdateGUIFromParameterNode")
    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    # Update node selectors and sliders
    self.ui.inputSurfaceSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputSurface"))
    self.ui.inputCenterlineSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCenterline"))
    self.ui.outputSurfaceSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputSurface"))
    
    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("InputSurface") and self._parameterNode.GetNodeReference("InputCenterline"):
      print("*")
    
      if not self._parameterNode.GetNodeReference("OpenSurface_ROIBox"):
        roiBoxReady = self.initializeROIBox()
        # initialize points locator used in the positioning of the ROI box  
        if roiBoxReady:
          if not self.pointsLocator:
            self.pointsLocator = vtk.vtkPointLocator() # could try using vtk.vtkStaticPointLocator() if need to optimize
            self.pointsLocator.SetDataSet(self._parameterNode.GetNodeReference("InputCenterline").GetPolyData())
            self.pointsLocator.BuildLocator() 
        # initialize output model if none is selected
      if not self._parameterNode.GetNodeReference("OutputSurface"):
        outputNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', 'open_model')
        self._parameterNode.SetNodeReferenceID("OutputSurface",outputNode.GetID())
        self.ui.outputSurfaceSelector.setCurrentNode(outputNode)
        # 
      
    if self._parameterNode.GetNodeReference("OpenSurface_ROIBox"):
      self.ui.applyButton.toolTip = "Clip surface with ROI" 
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = " to apply clip, first place ROI"
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
    
    self._parameterNode.SetNodeReferenceID("InputSurface", self.ui.inputSurfaceSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputCenterline", self.ui.inputCenterlineSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputSurface", self.ui.outputSurfaceSelector.currentNodeID)
    
    
    self._parameterNode.EndModify(wasModified)

  def initializeROIBox(self):
    # initialize the ROI box at index 0
    print("InitializeROIBox")
    try:
      # check if centerlinegeometry has already been computed, if not, compute it once
      centerlineModelNode = self._parameterNode.GetNodeReference("InputCenterline")
      if not centerlineModelNode.HasPointScalarName("FrenetTangent"):
        centerlineGeometryPolyData = self.logic.computeCenterlineGeometry(self.logic.polyDataFromNode(centerlineModelNode))
        centerlineModelNode.SetAndObserveMesh(centerlineGeometryPolyData)

      # compute plane normal to centerline
      plane_idx = 0
      planeNode = self.logic.createPlaneNormalToCenterline(self.logic.polyDataFromNode(centerlineModelNode), plane_idx, "OpenSurface_SlicePlane") 
      planeNode.SetHideFromEditors(1)
    
      # create ROI BOX markups node
      roiNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
      if not roiNode:
        roiNode = self.logic.createROIBox(planeNode.GetCenter(),planeNode.GetSize()[0],planeNode.GetSize()[0],planeNode.GetSize()[0],"OpenSurface_ROIBox")
        roiNode.GetDisplayNode().SetPointLabelsVisibility(False)
        roiNode.GetDisplayNode().SetPropertiesLabelVisibility(False)
        # add to parameter node
        self._parameterNode.SetNodeReferenceID("OpenSurface_ROIBox", roiNode.GetID())
      # get the roibox's planes
      roiPlanes = vtk.vtkPlanes()
      roiNode.GetPlanes(roiPlanes)
      
      # convert one of the roi planes to markupplane for registration
      roiPlane0 = roiPlanes.GetPlane(0)
      planeROINode = self.logic.createPlaneFromOriginAndNormal(roiPlane0.GetOrigin(),roiPlane0.GetNormal(),planeNode.GetSize()[0],"OpenSurface_ROIPlane")
      planeROINode.SetHideFromEditors(1)
      
      #align the roi to the plane normal to the centerline using the roi plane in the aligning process
      self.logic.alignPlanes(planeNode,planeROINode,roiNode)
      
      # remove nodes that are no longer necessary
      slicer.mrmlScene.RemoveNode(planeNode)
      slicer.mrmlScene.RemoveNode(planeROINode)

      # setup crosshair to get positionon centerline model. Position can be selected by moving the mouse while holding the shift+'r' key ( slicer<5.4) 
      # or the 'r'key (>= slicer 5.4). Code based on script repository
      crosshairNode=slicer.util.getNode("Crosshair")
      self.ROIPlacementObservationId = crosshairNode.AddObserver(slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent, self.onMouseMoved)
   
      # add observer for key presses
      interactor = slicer.app.layoutManager().threeDWidget(0).threeDView().interactor()
      self.keyPressObservationId = interactor.AddObserver(vtk.vtkCommand.KeyPressEvent, self.processEvent)
      # add observer for key releases
      self.keyReleaseObservationId = interactor.AddObserver(vtk.vtkCommand.KeyReleaseEvent, self.processEvent)


    except Exception as e:
      slicer.util.errorDisplay("Failed create ROI Box. Please make sure a centerline model is selected. Error: "+str(e))
      return False

    return True

  def processEvent(self,caller=None,event=None):
    interactor = slicer.app.layoutManager().threeDWidget(0).threeDView().interactor()
    if event == "KeyPressEvent":
      key = interactor.GetKeySym()
      if key.lower() == 'r':
        self.moveROIBox = True
    if event == "KeyReleaseEvent":
      self.moveROIBox = False 

  def onMouseMoved(self,observer, eventid):
    centerlineModelNode = self._parameterNode.GetNodeReference("InputCenterline")
    crosshairNode = slicer.util.getNode("Crosshair")
    ras=[0,0,0]
    crosshairNode.GetCursorPositionRAS(ras)
    closestPointId = self.pointsLocator.FindClosestPoint(ras)
    ras = centerlineModelNode.GetPolyData().GetPoint(closestPointId)
   
    if self.moveROIBox:
      # redraw ROIbox for clipping
      self.updateROIBox(closestPointId)   

 
  def updateROIBox(self, pointIndex):
    print("updateROIBox")
    # only update the ROI box if the pointIndex has changed
    slicePlaneLocation = int(self._parameterNode.GetParameter("SlicePlaneLocation"))
    if slicePlaneLocation == pointIndex:
      return
    else:
      # store new location in parameter node
      self._parameterNode.SetParameter("SlicePlaneLocation", str(pointIndex))
      
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
     
      # check if centerlinegeometry has already been computed, if not, compute it once
      centerlineModelNode = self._parameterNode.GetNodeReference("InputCenterline")
      if not centerlineModelNode.HasPointScalarName("FrenetTangent"):
        centerlineGeometryPolyData = self.logic.computeCenterlineGeometry(self.logic.polyDataFromNode(centerlineModelNode))
        centerlineModelNode.SetAndObserveMesh(centerlineGeometryPolyData)

      # Todo: move this to logic class
      roiNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
      
      planeNode = self.logic.createPlaneNormalToCenterline(self.logic.polyDataFromNode(centerlineModelNode), pointIndex, "OpenSurface_SlicePlane") 
      planeNode.SetHideFromEditors(1)
      
      # get the roibox's planes
      roiPlanes = vtk.vtkPlanes()
      roiNode.GetPlanes(roiPlanes)
      
      # convert one of the roi planes to markupplane  for registration
      roiPlane0 = roiPlanes.GetPlane(0)
      planeROINode = self.logic.createPlaneFromOriginAndNormal(roiPlane0.GetOrigin(),roiPlane0.GetNormal(),planeNode.GetSize()[0],"OpenSurface_ROIPlane")
      planeROINode.SetHideFromEditors(1)
      
      #align the roi to the plane normal to the centerline using the roi plane in the aligning process
      self.logic.alignPlanes(planeNode,planeROINode,roiNode)
      
      # resize ROIbox
      roiNode.SetSize(planeNode.GetSize()[0],planeNode.GetSize()[0],planeNode.GetSize()[0])

      # remove nodes that are no longer necessary
      slicer.mrmlScene.RemoveNode(planeNode)
      slicer.mrmlScene.RemoveNode(planeROINode)
      
 
   
  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

      # clip the model using the markupsROINode. Use the dynamic modeler module's ROI cut tool fo this.
      modelNode = self._parameterNode.GetNodeReference("InputSurface")
      roiNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
      outputNode = self._parameterNode.GetNodeReference("OutputSurface")      
      self.logic.clipROIFromModel(modelNode,roiNode,outputNode)
      # display outputnode and hide inputnode
      if modelNode is not outputNode:
      #  print("hide inputnode")
        modelNode.SetDisplayVisibility(0)
      outputNode.SetDisplayVisibility(1)
      outputNode.GetDisplayNode().SetOpacity(0.6)
      outputNode.GetDisplayNode().SetColor(0.5,0.9,0.88)
      
  

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
  
    
  def setParameterNode(self, parameterNode):
    """ Set the current parameter node and initialize all unset parameters to their default values """
    if self.parameterNode==parameterNode:
      return
    self.setDefaultParameters(parameterNode)
    self.parameterNode = parameterNode
    
  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("SlicePlaneLocation"):
      parameterNode.SetParameter("SlicePlaneLocation", "0")
    
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
  
  def createPlaneFromOriginAndNormal(self,origin,normal,size, nodename,parameterNode=None):
    """create a markups plane at the coordinates in origin with orientation orthogononal to the normal vector. If the plane node already exists it is updated with the passed origin and normal"""
    
    planeNode = slicer.mrmlScene.GetNodesByName(nodename).GetItemAsObject(0)
    if not planeNode:
        planeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsPlaneNode',nodename)
        if parameterNode:
          # add the plane to the parameternode
          parameterNode.SetNodeReferenceID(nodename,planeNode.GetID())
    
    # update node with the center, normal and size data
    planeNode.SetCenter(origin)
    planeNode.SetNormal(normal) 
    planeNode.SetSizeWorld(size,size)
    
    return planeNode
    
  def createPlaneNormalToCenterline(self,centerlinePolyData, planeIdx, nodename,parameterNode=None):
    """
    Create a markups plane normal to the centerline and display it in the current scene
    :param centerlinePolyData: Centerline model of vessel
    """
    from vtk.numpy_interface import dataset_adapter as dsa
    # TODO: replace this with slicer util methods
    pointdata = dsa.WrapDataObject(centerlinePolyData).PointData
    normaldata = pointdata['FrenetNormal']
    tangentdata = pointdata['FrenetTangent']
    points = dsa.WrapDataObject(centerlinePolyData).Points
    
    # plane coords and normal
    planeCenter = points[planeIdx,:]
    planeNormal = tangentdata[planeIdx,:]
    planeSize = 2*pointdata['Radius'][planeIdx]*1.5
    # create/update a markups plane normal to the centerline curve at the indexed location
    return self.createPlaneFromOriginAndNormal(planeCenter,planeNormal,planeSize,nodename,parameterNode)
    
   
  def createROIBox(self,center,xsize,ysize,zsize,nodeName):
    """ Create a square markups ROI box at the given center location and size
    """  
    roiNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsROINode', nodeName)
    # Update node with location and size of roi
    roiNode.SetCenter(center)
    roiNode.SetSizeWorld(xsize,ysize,zsize)
      
    return roiNode   

  def alignPlanes(self,plane0Node,plane1Node, transformableNode=None):
    """ Align two planes through rigid registration of the center, normal, and one corner point.
    apply and harden the transform to planeNode1 and, if provided, an additional  nNode.
    """
    # get plane corner points for registration
    plane0Corners = vtk.vtkPoints()
    plane0Node.GetPlaneCornerPoints(plane0Corners)
    
    plane1Corners = vtk.vtkPoints()
    plane1Node.GetPlaneCornerPoints(plane1Corners)
    
    #create fixed landmarks array
    fixedPointsArray = np.array([plane0Node.GetOrigin(),
                                 np.add(plane0Node.GetOrigin(),plane0Node.GetNormal()),
                                 plane0Corners.GetPoint(0)])
    
    movingPointsArray = np.array([plane1Node.GetOrigin(),
                                  np.subtract(plane1Node.GetOrigin(),plane1Node.GetNormal()),
                                  plane1Corners.GetPoint(0)])
    
    # registration
    import SimpleITK as sitk
    
    # use simpleITKs initializer to register the points
    initializer = sitk.LandmarkBasedTransformInitializerFilter()
    initializer.SetFixedLandmarks(fixedPointsArray.flatten()) # flatten the array as the initializer expects the point coordinates in one flat list [x1, y1, z1,x2,y2,z2, ...]
    initializer.SetMovingLandmarks(movingPointsArray.flatten())
    transform = initializer.Execute(sitk.VersorRigid3DTransform())
    # convert/cast to derived interface to access transformation matrix
    transform = sitk.VersorRigid3DTransform(transform)

    # get 4x4 numpy array representing the transformation matrix
    A = np.array(transform.GetMatrix()).reshape(3,3)
    c = np.array(transform.GetCenter())
    t = np.array(transform.GetTranslation())
    
    overall = np.eye(4)
    overall[0:3,0:3] = A
    overall[0:3,3] = -np.dot(A,c)+t+c
    
    matrix = slicer.util.vtkMatrixFromArray(overall)
    
     # create 3dslicer transform node
    transformNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTransformNode","ROITransform")
    #transformNode..SetHideFromEditors(1)
    transformNode.SetMatrixTransformFromParent(matrix)
    
    # apply transform to plane1
    plane1Node.SetAndObserveTransformNodeID(transformNode.GetID())
    plane1Node.HardenTransform()
   
    # apply transform to optional node 
    if transformableNode:
      transformableNode.SetAndObserveTransformNodeID(transformNode.GetID())
      transformableNode.HardenTransform()
    
    #remove transform node
    slicer.mrmlScene.RemoveNode(transformNode)
  
  def clipROIFromModel(self,inputModelNode,inputROINode,outputModelNode):
    """ Clip a model with a ROI
    """
    dynamicModelerNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLDynamicModelerNode")
    dynamicModelerNode.SetHideFromEditors(1)
    dynamicModelerNode.SetToolName("ROI cut")
    dynamicModelerNode.SetNodeReferenceID("ROICut.InputModel", inputModelNode.GetID())
    dynamicModelerNode.SetNodeReferenceID("ROICut.InputROI", inputROINode.GetID())
    dynamicModelerNode.SetNodeReferenceID("ROICut.OutputNegativeModel", outputModelNode.GetID())
    slicer.modules.dynamicmodeler.logic().RunDynamicModelerTool(dynamicModelerNode)


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
