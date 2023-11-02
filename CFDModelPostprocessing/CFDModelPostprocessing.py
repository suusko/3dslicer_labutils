import logging
import os
import numpy as np

import vtk
import qt
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# CFDModelPostprocessing
#

class CFDModelPostprocessing(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CFDModelPostprocessing"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["LabUtils"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["S.Korteland, dept of Biomedical Engineering, Erasmus MC, Rotterdam"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
This is a module to perform several postprocessing tasks for CFD models of blood flow through vessels.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""



#
# CFDModelPostprocessingWidget
#

class CFDModelPostprocessingWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CFDModelPostprocessing.ui'))
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
       
        # set colormap for all displays
        self.wssColormapName = "vtkMRMLColorTableNodeFileDivergingBlueRed.txt"

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CFDModelPostprocessingLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.filePathLineEdit.currentPathChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.loadButton.connect('clicked(bool)', self.onLoadButton)
        self.ui.scaleFactorLineEdit.connect('textEdited(str)', self.updateParameterNodeFromGUI)
        self.ui.scaleFactorCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.lpsToRasCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.endPointsMarkupsSelector.connect("currentNodeChanged(vtkMLMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.autoDetectEndPointsButton.connect('clicked(bool)',self.onAutoDetectEndPointsButton)
        self.ui.computeCenterlineButton.connect('clicked(bool)', self.onComputeCenterlineButton)
        self.ui.applyClipButton.connect('clicked(bool)', self.onApplyClipButton)
        self.ui.resetClipButton.connect('clicked(bool)', self.onResetClipButton)
        self.ui.saveClippedModelButton.connect('clicked(bool)',self.onSaveClippedModelButton)
        self.ui.endPointsROIMarkupsSelector.connect("currentNodeChanged(vtkMLMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.autoDetectEndPointsROIButton.connect('clicked(bool)',self.onAutoDetectEndPointsROIButton)
        self.ui.noCircBinSpinBox.connect('valueChanged(int)', self.updateParameterNodeFromGUI)
        self.ui.longBinSizeSpinBox.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
        self.ui.computeMapsButton.connect('clicked(bool)', self.onComputeMapsButton)
        self.ui.scalarSelectionComboBox.currentTextChanged.connect(self.onScalarSelected)
        self.ui.saveMapsButton.connect('clicked(bool)',self.onSaveMapsButton)

        # set layout to 3D view only
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
   
    
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
            # remove observers
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
        if self._parameterNode is not None and self.hasObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode):
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
        print("updateGUIFromParameterNode")
        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and slider
        self.ui.endPointsMarkupsSelector.setCurrentNode(self._parameterNode.GetNodeReference("EndPoints"))

        self.ui.endPointsROIMarkupsSelector.setCurrentNode(self._parameterNode.GetNodeReference("ROIEndPoints"))

        # Update buttons states and tooltips
        self.ui.filePathLineEdit.setCurrentPath(self._parameterNode.GetParameter("InputFilePath"))
        self.ui.scaleFactorCheckBox.checked = (self._parameterNode.GetParameter("UseScaleFactor") == "true")
        self.ui.scaleFactorLineEdit.enabled = (self._parameterNode.GetParameter("UseScaleFactor") == "true")
        self.ui.lpsToRasCheckBox.checked = (self._parameterNode.GetParameter("LPSToRAS") == "true")
        
        # update text fields
        self.ui.scaleFactorLineEdit.setText(self._parameterNode.GetParameter("ScaleFactor"))
        self.ui.longBinSizeSpinBox.value = float(self._parameterNode.GetParameter("LongitudinalPatchSize"))   
        self.ui.noCircBinSpinBox.value = int(self._parameterNode.GetParameter("CircularNumberOfPatches"))   

        # update display scalar 
        surfaceNode = self._parameterNode.GetNodeReference("SurfaceModel")
        if surfaceNode:
            # set visibility
            surfaceNode.GetDisplayNode().SetVisibility(1) 

            # enable centerline computation
            self.ui.endPointsMarkupsSelector.enabled = True
            self.ui.endPointsMarkupsPlaceWidget.enabled = True
            self.ui.autoDetectEndPointsButton.enabled = True
            self.ui.computeCenterlineButton.enabled = True

            # center 3Dview on the scene
            slicer.app.layoutManager().threeDWidget(0).threeDView().resetFocalPoint()
            # hide bounding box
            viewNode = slicer.app.layoutManager().threeDWidget(0).mrmlViewNode()
            viewNode.SetBoxVisible(0)
            viewNode.SetAxisLabelsVisible(0)
            # display orientation marker
            viewNode.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)

        # display inlet boundaries
        endPointsNode = self._parameterNode.GetNodeReference("EndPoints")
        if endPointsNode:
            self.updateInletRadioButtons(endPointsNode)
            
            # enable inlet radiobuttons groupbox
            self.ui.selectInletGroupBox.enabled = True

        # initialize/update clipping roi box
        if self._parameterNode.GetNodeReference("CenterlineModel"):
            if not self._parameterNode.GetNodeReference("OpenSurface_ROIBox"):
                roiBoxReady = self.initializeROIBox()
                # initialize points locator used in the positioning of the ROI box
                if roiBoxReady:
                    if not self.pointsLocator:
                        self.pointsLocator = vtk.vtkPointLocator() # could try using vtk.vtkStaticPointLocator() if need to optimize
                        self.pointsLocator.SetDataSet(self._parameterNode.GetNodeReference("CenterlineModel").GetPolyData())
                        self.pointsLocator.BuildLocator()
           
            self.ui.longBinSizeSpinBox.enabled = True
            self.ui.noCircBinSpinBox.enabled = True
            self.ui.computeMapsButton.enabled = True

            # hide endpointsnode
            endPointsNode.GetDisplayNode().SetVisibility(0)

        # set clip ROI button state
        if self._parameterNode.GetNodeReference("OpenSurface_ROIBox"):
            # enable clipping button
            self.ui.applyClipButton.enabled = True
            
        if self._parameterNode.GetNodeReference("ROISurfaceModel"):
            # enable reset button
            self.ui.resetClipButton.enabled = True
            self.ui.saveClippedModelButton.enabled = True
            # enable 2d map computation
            self.ui.endPointsROIMarkupsSelector.enabled = True
            self.ui.endPointsROIMarkupsPlaceWidget.enabled = True
            self.ui.autoDetectEndPointsROIButton.enabled = True
            # hide original surface model
            surfaceNode.GetDisplayNode().SetVisibility(0) 
        
        # display inlet boundaries for ROI model
        ROIEndPointsNode = self._parameterNode.GetNodeReference("ROIEndPoints")
        if ROIEndPointsNode:
            self.updateROIInletRadioButtons(ROIEndPointsNode)
            
            # enable inlet radiobuttons groupbox
            self.ui.selectROIInletGroupBox.enabled = True

            # hide centerline of original model
            centerlineModel = self._parameterNode.GetNodeReference("CenterlineModel")
            if centerlineModel:
                centerlineModel.GetDisplayNode().SetVisibility(0)

            # Hide ROI Box
            ROIBoxNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
            if ROIBoxNode:
                ROIBoxNode.SetDisplayVisibility(0)

        if self._parameterNode.GetNodeReference("SurfacePatchingModel"):
            self.ui.scalarSelectionComboBox.enabled = True
            self.updateScalarSelectionComboBox()
            # set the layout
            self.setupMapsLayout()
            # enable save button
            self.ui.saveMapsButton.enabled = True

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """
        
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        print("updateParameterNodeFromGUI")
        self._parameterNode.SetNodeReferenceID("EndPoints", self.ui.endPointsMarkupsSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("ROIEndPoints", self.ui.endPointsROIMarkupsSelector.currentNodeID)

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch
        
        self._parameterNode.SetParameter("InputFilePath",self.ui.filePathLineEdit.currentPath)
        self._parameterNode.SetParameter("ScaleFactor",self.ui.scaleFactorLineEdit.text)
        self._parameterNode.SetParameter("UseScaleFactor", "true" if self.ui.scaleFactorCheckBox.checked else "false")
        self._parameterNode.SetParameter("LPSToRAS", "true" if self.ui.lpsToRasCheckBox.checked else "false")
        self._parameterNode.SetParameter("LongitudinalPatchSize",str(self.ui.longBinSizeSpinBox.value))
        self._parameterNode.SetParameter("CircularNumberOfPatches",str(self.ui.noCircBinSpinBox.value))
        self._parameterNode.SetParameter("SelectedScalarForMapping", self.ui.scalarSelectionComboBox.currentText)
        self._parameterNode.EndModify(wasModified)

    def onLoadButton(self):
        """
        load surface file 
        """

        scaleFactor = float(self._parameterNode.GetParameter("ScaleFactor"))
        if not scaleFactor:
            scaleFactor = float(self.ui.scaleFactorLineEdit.text())

        with slicer.util.tryWithErrorDisplay("Failed to load file", waitCursor=True):

            filePath = self.ui.filePathLineEdit.currentPath
           
            fileExt = os.path.splitext(filePath)[1]
            print(fileExt)
            # load file using  different approaches based on the file extension
            if fileExt in ['.tec','.dat']:
                # try load file with vtk tecplot reader
                reader = vtk.vtkTecplotReader()
                reader.SetFileName(filePath)
                # multiblock to polydata
                geomFilter = vtk.vtkCompositeDataGeometryFilter()
                geomFilter.SetInputConnection(reader.GetOutputPort())
                
                transform = vtk.vtkTransform()  

                if self._parameterNode.GetParameter("UseScaleFactor") == "true":
                    # scale to mm and convert LPS (used in file) to RAS (used internally by 3Dslicer), i.e. negate the x and y coordinates
                    if self._parameterNode.GetParameter("LPSToRAS") == "true":
                        transform.Scale(-scaleFactor, -scaleFactor, scaleFactor) 
                    else:
                        transform.Scale(scaleFactor,scaleFactor,scaleFactor)
                else:
                    transform.Scale(1.0,1.0,1.0)
                transformFilter = vtk.vtkTransformFilter()
                transformFilter.SetInputConnection(geomFilter.GetOutputPort())
                transformFilter.SetTransform(transform)
                #transformFilter.Update()    
        
                # clean surface
                cleaner = vtk.vtkCleanPolyData()
                cleaner.SetInputConnection(transformFilter.GetOutputPort())
                cleaner.Update()
                    
                surfacePolyData = cleaner.GetOutput()
        
                # polydata to node
                surfaceNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', 'SurfaceModelNode')
                surfaceNode.SetAndObserveMesh(surfacePolyData)  
                if not surfaceNode.GetDisplayNode():
                    surfaceNode.CreateDefaultDisplayNodes()  
            else:
                # try loading file using slicer data loader
                surfaceNode = slicer.util.loadModel(filePath) 

            # save to parameter node
            self._parameterNode.SetNodeReferenceID("SurfaceModel",surfaceNode.GetID())

    def updateScalarSelectionComboBox(self):
        # update the scalar selection combobox with the available scalars
        print("updateScalarSelectionComboBox")
        surfaceNode = self._parameterNode.GetNodeReference("SurfacePatchingModel")
        #get the selected scalar, if present, before filling the combobox as this will overwrite the selected scalar to the first in the list
        selectedScalar = self._parameterNode.GetParameter("SelectedScalarForMapping")

        if not surfaceNode:
            return
        nScalars = self.ui.scalarSelectionComboBox.count
        if nScalars == 0:
            # fill the combobox
            # get pointdata scalars
            nPointDataScalars = surfaceNode.GetPolyData().GetPointData().GetNumberOfArrays()
            pointScalarList = []
            for i in range(nPointDataScalars):
                pointScalarList.append(surfaceNode.GetPolyData().GetPointData().GetArrayName(i))
              
            # get celldata scalars
            nCellDataScalars = surfaceNode.GetPolyData().GetCellData().GetNumberOfArrays()
            cellScalarList = []
            for i in range(nCellDataScalars):
                arrayName = surfaceNode.GetPolyData().GetCellData().GetArrayName(i)
                cellScalarList.append(f'{arrayName} (patched)')
            
            # clear combobox
            self.ui.scalarSelectionComboBox.clear()

            # fill combobox with list of selectable scalars
            self.ui.scalarSelectionComboBox.addItems(pointScalarList + cellScalarList) 
        
        if selectedScalar:
            # set selected scalar in the combobox
            self.ui.scalarSelectionComboBox.setCurrentText(selectedScalar)

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

    def onAutoDetectEndPointsROIButton(self):

        surfaceModelNode = self._parameterNode.GetNodeReference("ROISurfaceModel")
        endPointsNode = self._parameterNode.GetNodeReference("ROIEndPoints")
        if not endPointsNode:
            endPointsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode",
                    "CenterlineROIEndPoints")
            endPointsNode.CreateDefaultDisplayNodes()
            self._parameterNode.SetNodeReferenceID("ROIEndPoints", endPointsNode.GetID())
        # Make input surface semi-transparent to make all detected endpoints visible
        surfaceModelNode.GetDisplayNode().SetOpacity(0.8)
        
        self.autoDetectEndPoints(surfaceModelNode,endPointsNode)

        # display endpoint labels
        endPointsNode.SetControlPointLabelFormat("%d")
        # update control points with current format
        slicer.modules.markups.logic().RenameAllControlPointsFromCurrentFormat(endPointsNode)
        endPointsNode.GetDisplayNode().SetPointLabelsVisibility(True)

        # create radiobuttons so the user can select which endPoint should be the inlet
        self.updateROIInletRadioButtons(endPointsNode)

        # when user removes or adds point to the endpointsNode, recreate the inlet radiobuttons
        endPointsNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointAddedEvent,self.updateROIInletRadioButtons)
        endPointsNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent,self.updateROIInletRadioButtons)

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

    def updateROIInletRadioButtons(self,caller,event=None):
        endPointsNode = caller
        # clear existing widgets in the layout
        layout = self.ui.selectROIInletGroupBox.layout()
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
            self.ui.selectROIInletGroupBox.setLayout(layout)
        
        self.ROIinletRadioButtonsList=[]
        for i in range(endPointsNode.GetNumberOfControlPoints()):
            newRadioButton = qt.QRadioButton()
            newRadioButton.text=endPointsNode.GetNthControlPointLabel(i)
            self.ROIinletRadioButtonsList.append(newRadioButton)
            # check the radiobutton if its corresponding control point is unchecked to indicate the startpoint for centerline computation
            if not endPointsNode.GetNthControlPointSelected(i):
                newRadioButton.checked = True

             #connect event handler when the button is toggled
            newRadioButton.toggled.connect(self.onROIInletRadioButtonToggled)
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

    def onROIInletRadioButtonToggled(self,checked):
        if not checked:
            return
        else:
            endPointsNode = self._parameterNode.GetNodeReference("ROIEndPoints")
            # select all controlpoints, then deselect the one that was marked as inlet
            slicer.modules.markups.logic().SetAllControlPointsSelected(endPointsNode,True)
            
            # get the markupsnode controlpoint associated with the selected radio button and unselect it
            for (i,btn) in enumerate(self.ROIinletRadioButtonsList):
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
        centerlineModelNode = self._parameterNode.GetNodeReference("CenterlineModel")
        if not centerlineModelNode:
            centerlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode",'CenterlineModel')
            centerlineModelNode.SetAndObserveMesh(centerlinePolyData)
            self._parameterNode.SetNodeReferenceID("CenterlineModel", centerlineModelNode.GetID())
        else:
            centerlineModelNode.SetAndObserveMesh(centerlinePolyData)
        if not centerlineModelNode.GetDisplayNode():
            centerlineModelNode.CreateDefaultDisplayNodes()  
        centerlineModelNode.GetDisplayNode().SetVisibility(1) 
        centerlineModelNode.GetDisplayNode().SetLineWidth(5)
        # reduce opacity of surface model
        surfaceNode.GetDisplayNode().SetOpacity(0.6)

    def initializeROIBox(self):
        # initialize the ROI box at index 0
        print("InitializeROIBox")
        openSurfaceLogic = slicer.modules.opensurface.widgetRepresentation().self().logic
        try:
            # check if centerlinegeometry has already been computed, if not, compute it once
            centerlineModelNode = self._parameterNode.GetNodeReference("CenterlineModel")
            if not centerlineModelNode.HasPointScalarName("FrenetTangent"):
                centerlineGeometryPolyData = openSurfaceLogic.computeCenterlineGeometry(centerlineModelNode.GetPolyData())
                centerlineModelNode.SetAndObserveMesh(centerlineGeometryPolyData)

            # compute plane normal to centerline
            plane_idx = 0
            planeNode = openSurfaceLogic.createPlaneNormalToCenterline(centerlineModelNode.GetPolyData(), plane_idx, "OpenSurface_SlicePlane")
            planeNode.SetHideFromEditors(1)

            # create ROI BOX markups node
            roiNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
            if not roiNode:
                roiNode = openSurfaceLogic.createROIBox(planeNode.GetCenter(),planeNode.GetSize()[0],planeNode.GetSize()[0],planeNode.GetSize()[0],"OpenSurface_ROIBox")
                roiNode.GetDisplayNode().SetPointLabelsVisibility(False)
                roiNode.GetDisplayNode().SetPropertiesLabelVisibility(False)
                # add to parameter node
                self._parameterNode.SetNodeReferenceID("OpenSurface_ROIBox", roiNode.GetID())
            # get the roibox's planes
            roiPlanes = vtk.vtkPlanes()
            roiNode.GetPlanes(roiPlanes)

            # convert one of the roi planes to markupplane for registration
            roiPlane0 = roiPlanes.GetPlane(0)
            planeROINode = openSurfaceLogic.createPlaneFromOriginAndNormal(roiPlane0.GetOrigin(),roiPlane0.GetNormal(),planeNode.GetSize()[0],"OpenSurface_ROIPlane")
            planeROINode.SetHideFromEditors(1)

            #align the roi to the plane normal to the centerline using the roi plane in the aligning process
            openSurfaceLogic.alignPlanes(planeNode,planeROINode,roiNode)

            # remove nodes that are no longer necessary
            slicer.mrmlScene.RemoveNode(planeNode)
            slicer.mrmlScene.RemoveNode(planeROINode)

            # setup crosshair to get position on centerline model. Position can be selected by moving the mouse while holding down the shift key (only Slicer 5.2.2 and below). 
            # Code based on script repository
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
        centerlineModelNode = self._parameterNode.GetNodeReference("CenterlineModel")
        crosshairNode = slicer.util.getNode("Crosshair")
        ras=[0,0,0]
        crosshairNode.GetCursorPositionRAS(ras)
        closestPointId = self.pointsLocator.FindClosestPoint(ras)
        ras = centerlineModelNode.GetPolyData().GetPoint(closestPointId)

        if self.moveROIBox:
            # redraw ROIbox for clipping
            self.updateROIBox(closestPointId)


    def updateROIBox(self, pointIndex):
        openSurfaceLogic = slicer.modules.opensurface.widgetRepresentation().self().logic

        # only update the ROI box if the pointIndex has changed
        slicePlaneLocation = int(self._parameterNode.GetParameter("SlicePlaneLocation"))
        if slicePlaneLocation == pointIndex:
            return
        else:
            # store new location in parameter node
            self._parameterNode.SetParameter("SlicePlaneLocation", str(pointIndex))

        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            # check if centerlinegeometry has already been computed, if not, compute it once
            centerlineModelNode = self._parameterNode.GetNodeReference("CenterlineModel")
            if not centerlineModelNode.HasPointScalarName("FrenetTangent"):
                centerlineGeometryPolyData = openSurfaceLogic.computeCenterlineGeometry(centerlineModelNode.GetPolyData())
                centerlineModelNode.SetAndObserveMesh(centerlineGeometryPolyData)

            # Todo: move this to logic class
            roiNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")

            planeNode = openSurfaceLogic.createPlaneNormalToCenterline(centerlineModelNode.GetPolyData(), pointIndex, "OpenSurface_SlicePlane")
            planeNode.SetHideFromEditors(1)

            # get the roibox's planes
            roiPlanes = vtk.vtkPlanes()
            roiNode.GetPlanes(roiPlanes)

            # convert one of the roi planes to markupplane  for registration
            roiPlane0 = roiPlanes.GetPlane(0)
            planeROINode = openSurfaceLogic.createPlaneFromOriginAndNormal(roiPlane0.GetOrigin(),roiPlane0.GetNormal(),planeNode.GetSize()[0],"OpenSurface_ROIPlane")
            planeROINode.SetHideFromEditors(1)

            #align the roi to the plane normal to the centerline using the roi plane in the aligning process
            openSurfaceLogic.alignPlanes(planeNode,planeROINode,roiNode)

            # resize ROIbox
            roiNode.SetSize(planeNode.GetSize()[0],planeNode.GetSize()[0],planeNode.GetSize()[0])

            # remove nodes that are no longer necessary
            slicer.mrmlScene.RemoveNode(planeNode)
            slicer.mrmlScene.RemoveNode(planeROINode)
  
    def onApplyClipButton(self):
        """
        Clip the surface with the ROI box
        """
        openSurfaceLogic = slicer.modules.opensurface.widgetRepresentation().self().logic
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            # clip the model using the markupsROINode. Use the dynamic modeler module's ROI cut tool fo this.
            
            roiNode = self._parameterNode.GetNodeReference("OpenSurface_ROIBox")
            ROIModelNode = self._parameterNode.GetNodeReference("ROISurfaceModel")
            if not ROIModelNode:
                ROIModelNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', 'open_model')
                self._parameterNode.SetNodeReferenceID("ROISurfaceModel",ROIModelNode.GetID())
                # first time to clip, set the modelNode to start with
                inputModelNode = self._parameterNode.GetNodeReference("SurfaceModel")
            else: inputModelNode =ROIModelNode
               
            openSurfaceLogic.clipROIFromModel(inputModelNode,roiNode,ROIModelNode)
            # display outputnode and hide inputnode
            if inputModelNode is not ROIModelNode:
                #  print("hide inputnode")
                inputModelNode.SetDisplayVisibility(0)

            ROIModelNode.SetDisplayVisibility(1)
            ROIModelNode.GetDisplayNode().SetOpacity(0.6)
            ROIModelNode.GetDisplayNode().SetColor(0.5,0.9,0.88)

           

    def onResetClipButton(self):
        """reset the clipped model to the input model"""
        # reset the clipped model by deleting it
        ROIModelNode = self._parameterNode.GetNodeReference("ROISurfaceModel")
        if ROIModelNode:
            slicer.mrmlScene.RemoveNode(ROIModelNode)
        # set the visibility of the original model
        originalModelNode =self._parameterNode.GetNodeReference("SurfaceModel")
        originalModelNode.SetDisplayVisibility(1)
    
    def onSaveClippedModelButton(self):
        filePath = self.ui.filePathLineEdit.currentPath
        filePath_NoExt = os.path.splitext(filePath)[0]
        outFilePath = ''.join((filePath_NoExt,'_ROI.vtp'))
        ROIModelNode = self._parameterNode.GetNodeReference("ROISurfaceModel")
        slicer.util.saveNode(ROIModelNode,  outFilePath)

        # enable the centerline computation in the next section for map computation
        

    def onComputeMapsButton(self):
        """Compute 2D maps of selected model surface """
        
        from vtk.numpy_interface import dataset_adapter as dsa

        # Hide ROI box 
        ROIModelNode = self._parameterNode.GetNodeReference("ROISurfaceModel")
        if ROIModelNode:
            ROIModelNode.SetDisplayVisibility(0)
        
        # get the surface, either the ROI surface or the original surface
        if self._parameterNode.GetNodeReference("ROISurfaceModel"):
            # get the clipped model
            surfaceModelNode = self._parameterNode.GetNodeReference("ROISurfaceModel")
            # get the endPoints to recompute the centerline for the ROI model
            endPointsNode = self._parameterNode.GetNodeReference("ROIEndPoints")
            if not endPointsNode:
                slicer.util.errorDisplay("No endpoints detected for clipped surface model. Please make sure to compute endpoints before proceeding")
                return
            
            # compute centerline
            ExtractCenterlineLogic = slicer.modules.extractcenterline.widgetRepresentation().self().logic
            ClipBranchesLogic = slicer.modules.clipbranches.widgetRepresentation().self().logic

            # preprocess polydata to improve centerline computation
            preprocessedPolyData = self.getPreprocessedPolyData(surfaceModelNode)
            curveSamplingDistance = 1.0 # default
            centerlinePolyData, _ = ExtractCenterlineLogic.extractCenterline(preprocessedPolyData,endPointsNode,curveSamplingDistance)

        else:
            # use the original model
            surfaceModelNode = self._parameterNode.GetNodeReference("SurfaceModel")
            centerlineModelNode = self._parameterNode.GetNodeReference("CenterlineModel")
            centerlinePolyData = centerlineModelNode.GetPolyData()
            endPointsNode = self._parameterNode.GetNodeReference("EndPoints")
        
        # hide the models from the previous step
        surfaceModelNode.GetDisplayNode().SetVisibility(0)
        endPointsNode.SetDisplayVisibility(0)

        # get the patch sizes
        longitudinalPatchSize = float(self._parameterNode.GetParameter("LongitudinalPatchSize"))
        circularNumberOfPatches = int(self._parameterNode.GetParameter("CircularNumberOfPatches"))

        # compute centerline attributes (abscissa, angular metric)
        centerlineAttributesPolyData = self.logic.computeCenterlineAttributes(centerlinePolyData)
        
        # split centerlines into branches
        centerlineSplitPolyData = ClipBranchesLogic.computeCenterlineBranches(centerlineAttributesPolyData)
        
        # to node
        newCenterlineNode = self._parameterNode.GetNodeReference("CenterlineForMap")
        if not newCenterlineNode:
            newCenterlineNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', 'CenterlineForMap')
            self._parameterNode.SetNodeReferenceID("CenterlineForMap",newCenterlineNode.GetID())
        newCenterlineNode.SetAndObserveMesh(centerlineSplitPolyData)  
        if not newCenterlineNode.GetDisplayNode():
            newCenterlineNode.CreateDefaultDisplayNodes()   
        newCenterlineNode.GetDisplayNode().SetVisibility(1) 

        # compute bifurcation reference system along the centerline
        bifurcationRefSysPolyData = self.logic.computeBifurcationReferenceSystems(centerlineSplitPolyData)
        
        # split the surface into its constituent branches
        surfaceSplitPolyData = self.logic.splitSurface(surfaceModelNode.GetPolyData(),centerlineSplitPolyData)
        
        # compute branch metrics (Abscissametric and Angular metric)
        surfaceMetricsPolyData = self.logic.computeBranchMetrics(surfaceSplitPolyData, centerlineSplitPolyData)
        
        # metrics mapping to branches
        surfaceMappingPolyData = self.logic.computeBranchMapping(surfaceMetricsPolyData,centerlineSplitPolyData,bifurcationRefSysPolyData)
        
        # To node for display
        surfaceMappingNode = self._parameterNode.GetNodeReference("SurfaceMappingModel")
        if not surfaceMappingNode:
            surfaceMappingNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', 'WSSModelMappingNode')
        surfaceMappingNode.SetAndObserveMesh(surfaceMappingPolyData)  
        if not surfaceMappingNode.GetDisplayNode():
            surfaceMappingNode.CreateDefaultDisplayNodes()  
        
        # patching of surface mesh for the whole geometry
        (surfacePatchingPolyData,surfacePatched2DPolyData) = self.logic.computeBranchPatching(surfaceMappingPolyData,longitudinalPatchSize,circularNumberOfPatches)

        # to node for display
        surfacePatchingNode = self._parameterNode.GetNodeReference("SurfacePatchingModel")
        if not surfacePatchingNode:
            surfacePatchingNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', 'WSSModelPatchingNode')
        surfacePatchingNode.SetAndObserveMesh(surfacePatchingPolyData)  
        if not surfacePatchingNode.GetDisplayNode():
            surfacePatchingNode.CreateDefaultDisplayNodes()     
       

        # get the group ids of the different branches
        surfWrapper = dsa.WrapDataObject(surfaceMappingPolyData)
        groupIdsArray =  np.unique(surfWrapper.PointData.GetArray("GroupIds"))
        # save array to parameter node
        self._parameterNode.SetParameter("BranchIds",' '.join([str(x) for x in groupIdsArray] ))
        
        # create layout
        (view1Node, view2Node, view3Node) = self.setupMapsLayout()

        # set views for the nodes
        surfaceMappingNode.GetDisplayNode().AddViewNodeID(view2Node.GetID())
        surfacePatchingNode.GetDisplayNode().AddViewNodeID(view1Node.GetID())
        
        # in the second view, display the angular metric on the mapping node
        surfaceMappingNode.GetDisplayNode().SetActiveScalar("AngularMetric",vtk.vtkAssignAttribute.POINT_DATA)
        surfaceMappingNode.GetDisplayNode().SetVisibility(1)
        surfaceMappingNode.GetDisplayNode().SetOpacity(0.6)  
        

        surfaceMappingNode.GetDisplayNode().SetAndObserveColorNodeID("vtkMRMLColorTableNodeFileViridis.txt")
        colorLegendDisplayNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(surfaceMappingNode)
        colorLegendDisplayNode.SetTitleText(surfaceMappingNode.GetDisplayNode().GetActiveScalarName())

        # add a display node for view 3to the mapping node
        groupIdsDisplayNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelDisplayNode')
        groupIdsDisplayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeFileViridis.txt")
        groupIdsDisplayNode.AddViewNodeID(view3Node.GetID())
        groupIdsDisplayNode.SetActiveScalar("GroupIds",vtk.vtkAssignAttribute.POINT_DATA)
        groupIdsDisplayNode.ScalarVisibilityOn()
        surfaceMappingNode.AddAndObserveDisplayNodeID(groupIdsDisplayNode.GetID())
        groupIdsDisplayNode.SetVisibility(1)
       
        # loop over the branches
        # split and analyse the branches separately
        for branchId in groupIdsArray:
            
            print(branchId)
            surfaceBranchMappingPolyData = self.logic.splitSurface(surfaceMappingPolyData,centerlineSplitPolyData,groupIds=[branchId])
            # patching of surface mesh and attributes
            try:
                (surfaceBranchPatchingPolyData, surfaceBranchPatchedPolyData) = self.logic.computeBranchPatching(surfaceBranchMappingPolyData, longitudinalPatchSize,circularNumberOfPatches)
            except Exception as e:
                slicer.util.errorDisplay(f"Failed to compute mapping for branch {branchId}. Error: {str(e)}. Continuing with next branch")
                continue    
        
            #print(surfaceBranchPatchedPolyData)
            surfaceName = f'Branch{branchId}PatchingModel'
            # to node
            surfaceBranchPatchingNode = self._parameterNode.GetNodeReference(surfaceName)
            if not surfaceBranchPatchingNode:
                surfaceBranchPatchingNode= slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode', surfaceName)
            surfaceBranchPatchingNode.SetAndObserveMesh(surfaceBranchPatchingPolyData)  
            if not surfaceBranchPatchingNode.GetDisplayNode():
                surfaceBranchPatchingNode.CreateDefaultDisplayNodes()
            # set the viewnode ID for the view to display this node in
            surfaceBranchPatchingNode.GetDisplayNode().AddViewNodeID(view1Node.GetID())
            surfaceBranchPatchingNode.GetDisplayNode().SetVisibility(0)  # hide the node
            # save node to parameter node
            self._parameterNode.SetNodeReferenceID(surfaceName,surfaceBranchPatchingNode.GetID())

            # store patched data in volumenode
            vol2DName = f'Branch{branchId}_2DPatchedModel'
            surface2DPatchingNode = self._parameterNode.GetNodeReference(vol2DName)
            if not surface2DPatchingNode:
                surface2DPatchingNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode', vol2DName)
            surface2DPatchingNode.SetAndObserveImageData(surfaceBranchPatchedPolyData);
            # save node to parameter node
            self._parameterNode.SetNodeReferenceID(vol2DName,surface2DPatchingNode.GetID())


        # save to parameter node (save this node last as it is used to update the GUI, which requires the 2D map computations for the branches to 
        # be saved to the parameter node already)
        self._parameterNode.SetNodeReferenceID("SurfaceMappingModel",surfaceMappingNode.GetID())
        self._parameterNode.SetNodeReferenceID("SurfacePatchingModel",surfacePatchingNode.GetID())

        # display endpoints node in view2
        endPointsNode.GetDisplayNode().AddViewNodeID(view2Node.GetID())        
        endPointsNode.SetDisplayVisibility(1)

        # display node in view2
        newCenterlineNode.GetDisplayNode().AddViewNodeID(view2Node.GetID())


        # link the 3DViews
        view1Node.LinkedControlOn()

        # reset views, rotate to view from anterior
        threeDView0 =  slicer.app.layoutManager().threeDWidget(0).threeDView()
        threeDView1 =  slicer.app.layoutManager().threeDWidget(1).threeDView()
        threeDView2 =  slicer.app.layoutManager().threeDWidget(2).threeDView()
        threeDView0.rotateToViewAxis(3)
        threeDView0.resetCamera()
        threeDView1.rotateToViewAxis(3)
        threeDView1.resetCamera()
        threeDView2.rotateToViewAxis(3)
        threeDView2.resetCamera()
        

    def setupMapsLayout(self):
        # get branch Ids from parameter node
        branchIds = [int(s) for s in self._parameterNode.GetParameter("BranchIds").split(' ')]
        nBranches = len(branchIds)
        # create custom layout for display
        startString = """
            <layout type="horizontal" split="true">
             <item splitSize="300">
              <view class="vtkMRMLViewNode" singletontag="1">
               <property name="viewlabel" action="default">1</property>
               <property name=\"viewcolor\" action=\"default\">#F34A33</property>"
              </view>
             </item>
             <item splitSize="300">
             <layout type="vertical" split="true">
             <item splitSize="500">
              <view class="vtkMRMLViewNode" singletontag="2">
               <property name="viewlabel" action="default">2</property>
               <property name=\"viewcolor\" action=\"default\">#F34A33</property>"
              </view>
             </item>
             <item splitSize="500">
              <view class="vtkMRMLViewNode" singletontag="3">
               <property name="viewlabel" action="default">3</property>
               <property name=\"viewcolor\" action=\"default\">#F34A33</property>"
              </view>
             </item>
             </layout>
             </item>
             <item splitSize="400">
              <layout type="tab">"""
        
        branchStringList = [None]*nBranches
        for i in range(nBranches):
            branchId = branchIds[i]
            branchStringList[i] = (f""" <item name="Branch {branchId}">
            <view class="vtkMRMLSliceNode" singletontag="SliceView{i+1}">
                 <property name="orientation" action="default">Axial</property>
                 <property name="viewlabel" action="default">Branch {branchId} 2D Map</property>
                 <property name="viewcolor" action="default">#F34A33</property>
                </view>
               </item>""")

        endString= """</layout>
             </item>
            </layout>
            """
        
        customLayout = startString + ''.join(branchStringList)+endString

        # Built-in layout IDs are all below 100, so you can choose any large random number
        # for your custom layout ID.
        customLayoutId=501
        
        layoutManager = slicer.app.layoutManager()
        layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(customLayoutId, customLayout)
        layoutManager.setLayout(customLayoutId)# 3D and table view
        
        # references to view nodes
        view1Node = slicer.util.getNode("View1")
        view2Node = slicer.util.getNode("View2")
        view3Node = slicer.util.getNode("View3")
        # set the views
        # hide bounding box
        view1Node.SetBoxVisible(0)
        view1Node.SetAxisLabelsVisible(0)
        # display orientation marker
        view1Node.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)
        # hide bounding box
        view2Node.SetBoxVisible(0)
        view2Node.SetAxisLabelsVisible(0)
        # display orientation marker
        view2Node.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)
        # hide bounding box
        view3Node.SetBoxVisible(0)
        view3Node.SetAxisLabelsVisible(0)
        # display orientation marker
        view3Node.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)



        return(view1Node, view2Node, view3Node)

    def onScalarSelected(self,scalarName):
        # save to parameter node
        self._parameterNode.SetParameter("SelectedScalarForMapping",scalarName)
        print("onScalarSelected")
        #print(scalarName)
        groupIdsArray = [int(s) for s in self._parameterNode.GetParameter("BranchIds").split(' ')]

        # display the selected scalar on the 3D geometry
        surfacePatchingNode = self._parameterNode.GetNodeReference("SurfacePatchingModel")
        # check whether regular or patched scalar was selected
        if scalarName.endswith(' (patched)'):
            # use the patched (i.e. celldata) variable
            activeScalar = scalarName.replace(' (patched)', "") # remove the (patched) substring
            surfacePatchingNode.GetDisplayNode().SetActiveScalar(activeScalar,vtk.vtkAssignAttribute.CELL_DATA)
        else:
            activeScalar = scalarName
            # the regular/original (i.e. pointdata) scalar was selected
            surfacePatchingNode.GetDisplayNode().SetActiveScalar(activeScalar,vtk.vtkAssignAttribute.POINT_DATA)
        surfacePatchingNode.GetDisplayNode().SetAndObserveColorNodeID(self.wssColormapName)
        surfacePatchingNode.GetDisplayNode().ScalarVisibilityOn()
        colorLegendDisplayNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(surfacePatchingNode)
        colorLegendDisplayNode.SetTitleText(surfacePatchingNode.GetDisplayNode().GetActiveScalarName())

        # display the 2D maps per branch
        for i,branchId in enumerate(groupIdsArray):
            
            vol2DName = f'Branch{branchId}_2DPatchedModel'
            surface2DPatchedNode = self._parameterNode.GetNodeReference(vol2DName)
            # get out the imagedata
            imgdata = surface2DPatchedNode.GetImageData()
            # create 2D map of selected scalar
            branch2DMap= self.logic.extractVariableMap(imgdata,activeScalar)
            
            # store to node
            map2DName = f'Branch{branchId}_2D_Map'
            map2DNode = self._parameterNode.GetNodeReference(map2DName)
            if not map2DNode:
                map2DNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode",map2DName)
                # to parameter node
                self._parameterNode.SetNodeReferenceID(map2DName,map2DNode.GetID())
                
        
            # show 2D color map
            slicer.util.updateVolumeFromArray(map2DNode, branch2DMap)
            
            viewNode = slicer.util.getNode(f"SliceView{i+1}").GetID()
            slicer.app.layoutManager().sliceWidget(f"SliceView{i+1}").sliceLogic().GetSliceCompositeNode().SetForegroundVolumeID(map2DNode.GetID())  # setvolume node as the foreground volume of the SliceView1 slice widget.
            # Add viewnode
            map2DNode.GetDisplayNode().AddViewNodeID(viewNode)
            map2DNode.GetDisplayNode().SetInterpolate(0)
            # get scalar range
            
            

            # This works from Slicer version 5.4.0 on
            map2DNode.GetDisplayNode().SetAndObserveColorNodeID(self.wssColormapName)
            cldNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(map2DNode)
            cldNode.SetTitleText(activeScalar)
            # toggle displaynode scalar range for display to force opdate of color legend range
            map2DNode.GetDisplayNode().SetScalarRangeFlag(0) # manual range
            map2DNode.GetDisplayNode().SetScalarRangeFlag(1) # auto/data scalar range


            # force and update of the view
            slicer.app.layoutManager().sliceWidget(f"SliceView{i+1}").sliceLogic().GetSliceNode().Modified()
            

        # enforce re-rendering of the views
        slicer.util.forceRenderAllViews()

        # reset slice views
        slicer.util.resetSliceViews()

           
    def onSaveMapsButton(self):
        import ScreenCapture

        # path to save to
        filePath = self.ui.filePathLineEdit.currentPath
        filePath_NoExt = os.path.splitext(filePath)[0]

        # save the complete 3D geometry with mapped data
        surfacePatchingNode = self._parameterNode.GetNodeReference("SurfacePatchingModel")
        outFilePath = ''.join((filePath_NoExt,f'_patching.vtp'))
        slicer.util.saveNode(surfacePatchingNode,  outFilePath)
            

        # ids of branches to save
        groupIdsArray = [int(s) for s in self._parameterNode.GetParameter("BranchIds").split(' ')]
        # loop over all branches
        for i,branchId in enumerate(groupIdsArray):
            # save 3D patched surfaces to file 
            surfacePatchingName =  f'Branch{branchId}PatchingModel'
            surfacePatchingModel = self._parameterNode.GetNodeReference(surfacePatchingName)
            outFilePath = ''.join((filePath_NoExt,f'_Branch{branchId}_patching.vtp'))
            slicer.util.saveNode(surfacePatchingModel,  outFilePath)
            
            # save results for selected scalar to file
            #save 2D wss maps to .csv, prox at the bottom, dist at the top
            selectedScalarName = self._parameterNode.GetParameter('SelectedScalarForMapping')
            map2DName = f'Branch{branchId}_2D_Map'
            map2DNode = self._parameterNode.GetNodeReference(map2DName)
            branch2DMap = np.squeeze(slicer.util.arrayFromVolume(map2DNode))
            outFilePath = ''.join((filePath_NoExt,f'_Branch{branchId}_{selectedScalarName}_2DMap.csv'))
            np.savetxt(outFilePath, np.fliplr(np.flipud(branch2DMap)), delimiter=",",fmt='%1.3f')

            # save screen captures to file
            outFilePath = ''.join((filePath_NoExt,f'_Branch{branchId}_{selectedScalarName}_2DMap.png'))
            view = slicer.app.layoutManager().sliceWidget(f"SliceView{i+1}").sliceView()
            # Capture a screenshot
            cap = ScreenCapture.ScreenCaptureLogic()
            cap.captureImageFromView(view, outFilePath)
            
# CFDModelPostprocessingLogic
#

class CFDModelPostprocessingLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

        self.radiusArrayName = 'Radius'
        self.blankingArrayName = 'Blanking'
        self.groupIdsArrayName = 'GroupIds'
        self.normalsArrayName = 'ParallelTransportNormals'
        self.abscissaArrayName = 'Abscissas'
        self.angularMetricArrayName = 'AngularMetric'
        self.abscissaMetricArrayName = 'AbscissaMetric'
        self.tractIdsArrayName = 'TractIds'
        self.centerlineIdsArrayName = 'CenterlineIds'
        self.parallelTransportNormalsArrayName = 'ParallelTransportNormals'
        self.referenceSystemsNormalArrayName = 'Normal'
        self.referenceSystemsUpNormalArrayName = 'UpNormal'
        self.boundaryMetricArrayName = 'BoundaryMetric' 
        self.harmonicMappingArrayName = 'HarmonicMapping'
        self.stretchedMappingArrayName = 'StretchedMapping' 
        self.longitudinalMappingArrayName = 'StretchedMapping'
        self.circularMappingArrayName = 'AngularMetric' 
        self.longitudinalPatchNumberArrayName = 'Slab'
        self.circularPatchNumberArrayName = 'Sector'
        self.patchAreaArrayName = 'PatchArea'

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        
        if not parameterNode.GetParameter("InputFilePath"):
            parameterNode.SetParameter("InputFilePath","")
        if not parameterNode.GetParameter("ScaleFactor"):
            parameterNode.SetParameter("ScaleFactor","1000")
        if not parameterNode.GetParameter("UseScaleFactor"):
            parameterNode.SetParameter("UseScaleFactor","false")
        if not parameterNode.GetParameter("LPSToRAS"):
            parameterNode.SetParameter("LPSToRAS","false")
        if not parameterNode.GetParameter("SlicePlaneLocation"):
            parameterNode.SetParameter("SlicePlaneLocation", "0")
        if not parameterNode.GetParameter("LongitudinalPatchSize"):
            parameterNode.SetParameter("LongitudinalPatchSize", "1.0")
        if not parameterNode.GetParameter("CircularNumberOfPatches"):
            parameterNode.SetParameter("CircularNumberOfPatches", "8") 
        if not parameterNode.GetParameter("BranchIds"):
            parameterNode.SetParameter("BranchIds","")   
        if not parameterNode.GetParameter("SelectedScalarForMapping"):
            parameterNode.SetParameter("SelectedScalarForMapping","")
            
    def computeBifurcationReferenceSystems(self,centerlinePolyData):
        """ compute bifurcation reference systems. Based on vmtkbifurcationreferencesystems pyscript"""
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        
        bifRefSystems = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBifurcationReferenceSystems()
        bifRefSystems.SetInputData(centerlinePolyData)
        bifRefSystems.SetRadiusArrayName(self.radiusArrayName)
        bifRefSystems.SetBlankingArrayName(self.blankingArrayName)
        bifRefSystems.SetGroupIdsArrayName(self.groupIdsArrayName)
        bifRefSystems.SetNormalArrayName(self.referenceSystemsNormalArrayName)
        bifRefSystems.SetUpNormalArrayName(self.referenceSystemsUpNormalArrayName)
        bifRefSystems.Update()
        
        return bifRefSystems.GetOutput()

    def splitSurface(self,surfacePolyData,centerlinePolyData,groupIds=None):
        """ split polysurface into branches based on split centerline. Based on vmtkbranchclipper pyscript"""
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        
        clipper = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlineGroupsClipper()
        clipper.SetInputData(surfacePolyData)
        clipper.SetCenterlines(centerlinePolyData)
        clipper.SetCenterlineGroupIdsArrayName(self.groupIdsArrayName)
        clipper.SetGroupIdsArrayName(self.groupIdsArrayName)
        clipper.SetCenterlineRadiusArrayName(self.radiusArrayName)
        clipper.SetBlankingArrayName(self.blankingArrayName)
        clipper.SetCutoffRadiusFactor(1E16)
        clipper.SetClipValue(0.0)
        clipper.SetUseRadiusInformation(1)
        if groupIds:
            groupIdsList = vtk.vtkIdList()
            for groupId in groupIds:
                groupIdsList.InsertNextId(groupId)
            clipper.SetCenterlineGroupIds(groupIdsList)
            clipper.ClipAllCenterlineGroupIdsOff()  
        else:
            clipper.ClipAllCenterlineGroupIdsOn() # clip all branches 
        clipper.GenerateClippedOutputOff() # not insideout
        clipper.Update()
        
        return clipper.GetOutput()
        
    def computeBranchMetrics(self,surfacePolyData,centerlinePolyData):
        """ compute metrics, based on vmtkbranchmetrics pyscript"""
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        
        # compute angular metric
        angularMetricFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlineAngularMetricFilter()
        angularMetricFilter.SetInputData(surfacePolyData)
        angularMetricFilter.SetMetricArrayName(self.angularMetricArrayName)
        angularMetricFilter.SetGroupIdsArrayName(self.groupIdsArrayName)
        angularMetricFilter.SetCenterlines(centerlinePolyData)
        angularMetricFilter.SetRadiusArrayName(self.radiusArrayName)
        angularMetricFilter.SetCenterlineNormalsArrayName(self.normalsArrayName)
        angularMetricFilter.SetCenterlineGroupIdsArrayName(self.groupIdsArrayName)
        angularMetricFilter.SetCenterlineTractIdsArrayName(self.tractIdsArrayName)
        angularMetricFilter.UseRadiusInformationOff()
        angularMetricFilter.IncludeBifurcationsOff()
        angularMetricFilter.SetBlankingArrayName(self.blankingArrayName)
        angularMetricFilter.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        angularMetricFilter.Update()
        
        # compute abscissa metric
        abscissaMetricFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlineAbscissaMetricFilter()
        abscissaMetricFilter.SetInputData(angularMetricFilter.GetOutput())
        abscissaMetricFilter.SetMetricArrayName(self.abscissaMetricArrayName)
        abscissaMetricFilter.SetGroupIdsArrayName(self.groupIdsArrayName)
        abscissaMetricFilter.SetCenterlines(centerlinePolyData)
        abscissaMetricFilter.SetRadiusArrayName(self.radiusArrayName)
        abscissaMetricFilter.SetAbscissasArrayName(self.abscissaArrayName)
        abscissaMetricFilter.SetCenterlineGroupIdsArrayName(self.groupIdsArrayName)
        abscissaMetricFilter.SetCenterlineTractIdsArrayName(self.tractIdsArrayName)
        abscissaMetricFilter.UseRadiusInformationOff()
        abscissaMetricFilter.IncludeBifurcationsOn()
        abscissaMetricFilter.SetBlankingArrayName(self.blankingArrayName)
        abscissaMetricFilter.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        abscissaMetricFilter.Update()
        
        return abscissaMetricFilter.GetOutput()
        
    def computeBranchMapping(self, surfacePolyData, centerlinePolyData,referenceSystems):
        """ compute branch mapping, based on vmtkbrancmapping pyscript"""
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        import vtkvmtkDifferentialGeometryPython as vtkvmtkDifferentialGeometry
                
        boundaryMetricFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataReferenceSystemBoundaryMetricFilter()
        boundaryMetricFilter.SetInputData(surfacePolyData)
        boundaryMetricFilter.SetBoundaryMetricArrayName(self.boundaryMetricArrayName)
        boundaryMetricFilter.SetGroupIdsArrayName(self.groupIdsArrayName)
        boundaryMetricFilter.SetCenterlines(centerlinePolyData)
        boundaryMetricFilter.SetCenterlineAbscissasArrayName(self.abscissaArrayName)
        boundaryMetricFilter.SetCenterlineRadiusArrayName(self.radiusArrayName)
        boundaryMetricFilter.SetCenterlineGroupIdsArrayName(self.groupIdsArrayName)
        boundaryMetricFilter.SetCenterlineTractIdsArrayName(self.tractIdsArrayName)
        boundaryMetricFilter.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        boundaryMetricFilter.SetReferenceSystems(referenceSystems)
        boundaryMetricFilter.SetReferenceSystemGroupIdsArrayName(self.groupIdsArrayName)
        boundaryMetricFilter.Update()

        harmonicMappingFilter = vtkvmtkDifferentialGeometry.vtkvmtkPolyDataMultipleCylinderHarmonicMappingFilter()
        harmonicMappingFilter.SetInputConnection(boundaryMetricFilter.GetOutputPort())
        harmonicMappingFilter.SetHarmonicMappingArrayName(self.harmonicMappingArrayName)
        harmonicMappingFilter.SetGroupIdsArrayName(self.groupIdsArrayName)
        harmonicMappingFilter.Update()

        
        stretchFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataStretchMappingFilter()
        stretchFilter.SetInputConnection(harmonicMappingFilter.GetOutputPort())
        stretchFilter.SetStretchedMappingArrayName(self.stretchedMappingArrayName)
        stretchFilter.SetHarmonicMappingArrayName(self.harmonicMappingArrayName)
        stretchFilter.SetGroupIdsArrayName(self.groupIdsArrayName)
        stretchFilter.SetMetricArrayName(self.abscissaMetricArrayName)
        stretchFilter.SetBoundaryMetricArrayName(self.boundaryMetricArrayName)
        stretchFilter.UseBoundaryMetricOn()
        stretchFilter.Update()

        return stretchFilter.GetOutput()
        
    def computeBranchPatching(self,surfacePolyData,longitudinalPatchSize, circularNumberOfPatches):
        """ compute patching of surface and attributes, based on vmtkbranchmapping pyscript """
        
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        
        patchSize = [longitudinalPatchSize, 1.0/float(circularNumberOfPatches)]
        
        patchingFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataPatchingFilter()
        patchingFilter.SetInputData(surfacePolyData)
        patchingFilter.SetCircularPatching(1)
        patchingFilter.SetUseConnectivity(1)
        patchingFilter.SetLongitudinalMappingArrayName(self.longitudinalMappingArrayName)
        patchingFilter.SetCircularMappingArrayName(self.circularMappingArrayName)
        patchingFilter.SetLongitudinalPatchNumberArrayName(self.longitudinalPatchNumberArrayName)
        patchingFilter.SetCircularPatchNumberArrayName(self.circularPatchNumberArrayName)
        patchingFilter.SetPatchAreaArrayName(self.patchAreaArrayName)
        patchingFilter.SetGroupIdsArrayName(self.groupIdsArrayName)
        patchingFilter.SetPatchSize(patchSize)
        patchingFilter.Update()

        return (patchingFilter.GetOutput(), patchingFilter.GetPatchedData())
        
    def flattenMappedSurface(mappedSurfacePolyData):
        # code based on discussion at http:
    
        # requires surface mapped with vmtkBranchMapping 
        # as we need the AngularMetric and the StretchedMapping arrays
        numberofpoints = mappedSurfacePolyData.GetNumberOfPoints()
        points = vtk.vtkPoints()
        points.SetNumberOfPoints(numberofpoints)    

        for i in range(numberofpoints):
        
            pointx =mapped_surface.GetPointData().GetArray(self.angularMetricArrayName).GetValue(i)
            pointy = mapped_surface.GetPointData().GetArray(self.stretchedMappingArrayName).GetValue(i)
            pointz = 0.0
            point = (pointx, pointy, pointz)
            points.SetPoint(i,point)

        output = vtk.vtkPolyData()
        output.DeepCopy(mappedSurfacePolyData)
        output.SetPoints(points)

        return output 

    def extractVariableMap(self,patched2DImage,variableName):
        from vtk.numpy_interface import dataset_adapter as dsa
        imwrapped = dsa.WrapDataObject(patched2DImage)
        patchVariableData = np.squeeze(imwrapped.PointData.GetArray(variableName).reshape(patched2DImage.GetDimensions(),order='F')).T
        #patchStretchedMappingData = np.squeeze(imwrapped.PointData.GetArray('StretchedMapping').reshape(surface_patched_2D.GetDimensions(),order='F')).T
        #patchAngularmetricData = np.squeeze(imwrapped.PointData.GetArray('AngularMetric').reshape(surface_patched_2D.GetDimensions(),order='F')).T
        
        return patchVariableData 
    
    def extractCenterlineGroup(self,centerlinePolyData,groupId):
        """ extract single centerline based on groupID
            returns dictionary with points and pointIds
        """
    
        clData = self.centerlineToNumpy(centerlinePolyData)
        # get the points corresponding to the groupId
        groupIdIdx = np.where(clData['CellData']['GroupIds']==groupId)[0][0]
        pointIds = clData['CellData']['CellPointIds'][groupIdIdx]
        points = clData['Points'][pointIds]
        centerlineData = dict()
        centerlineData['PointIds'] = pointIds
        centerlineData['Points'] = points
    
        return centerlineData
    
    def computeCenterlineAttributes(self, centerlinePolyData):
        """ compute centerline attributes such as AbscissaMetric,AngularMetric 
         and ParallelTransportNormals
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        attributesFilter = vtkvmtkComputationalGeometry.vtkvmtkCenterlineAttributesFilter()
        attributesFilter.SetInputData(centerlinePolyData)
        attributesFilter.SetAbscissasArrayName(self.abscissaArrayName)
        attributesFilter.SetParallelTransportNormalsArrayName(self.parallelTransportNormalsArrayName)
        attributesFilter.Update()
    
        return attributesFilter.GetOutput()
#
# CFDModelPostprocessingTest
#

class CFDModelPostprocessingTest(ScriptedLoadableModuleTest):
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
        self.test_CFDModelPostprocessing1()

    def test_CFDModelPostprocessing1(self):
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
        inputVolume = SampleData.downloadSample('CFDModelPostprocessing1')
        self.delayDisplay('Loaded test data set')

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = CFDModelPostprocessingLogic()

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
