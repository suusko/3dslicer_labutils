import logging
import os

import vtk

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

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)
        self.ui.surfaceVariablesDisplayWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CFDModelPostprocessingLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.loadButton.connect('clicked(bool)', self.onLoadButton)
        self.ui.scaleFactorLineEdit.connect('textEdited(str)', self.updateParameterNodeFromGUI)
        self.ui.scaleFactorCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.lpsToRasCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        
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

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
      
        # Update buttons states and tooltips
        self.ui.scaleFactorCheckBox.checked = (self._parameterNode.GetParameter("UseScaleFactor") == "true")
        self.ui.scaleFactorLineEdit.enabled = (self._parameterNode.GetParameter("UseScaleFactor") == "true")
        self.ui.lpsToRasCheckBox.checked = (self._parameterNode.GetParameter("LPSToRAS") == "true")
        
        # update text fields
        self.ui.scaleFactorLineEdit.setText(self._parameterNode.GetParameter("ScaleFactor"))


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
        
        self._parameterNode.SetParameter("ScaleFactor",self.ui.scaleFactorLineEdit.text)
        self._parameterNode.SetParameter("UseScaleFactor", "true" if self.ui.scaleFactorCheckBox.checked else "false")
        self._parameterNode.SetParameter("LPSToRAS", "true" if self.ui.lpsToRasCheckBox.checked else "false")
        
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
            
            # set visibility
            surfaceNode.GetDisplayNode().SetVisibility(1) 

            # display scalars
            surfaceNode.GetDisplayNode().ScalarVisibilityOn()
            # first scalar in list as active scalar
            firstScalarName = surfaceNode.GetPolyData().GetPointData().GetArrayName(0)
            surfaceNode.GetDisplayNode().SetActiveScalar(firstScalarName,vtk.vtkAssignAttribute.POINT_DATA)
            # set and display color legend
            surfaceNode.GetDisplayNode().SetAndObserveColorNodeID("vtkMRMLColorTableNodeFileViridis.txt")
            slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(surfaceNode)
                
            # set in display widget
            self.ui.surfaceVariablesDisplayWidget.enabled = True
            self.ui.surfaceVariablesDisplayWidget.setMRMLDisplayNode(surfaceNode.GetDisplayNode())                

            # Center view
            threeDView=slicer.app.layoutManager().threeDWidget(0).threeDView()
            # center 3Dview on the scene
            threeDView.resetFocalPoint()
            # hide bounding box
            viewNode = slicer.app.layoutManager().threeDWidget(0).mrmlViewNode()
            viewNode.SetBoxVisible(0)
            viewNode.SetAxisLabelsVisible(0)
            # display orientation marker
            viewNode.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeHuman)
    
#
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

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("ScaleFactor"):
            parameterNode.SetParameter("ScaleFactor","1000")
        if not parameterNode.GetParameter("UseScaleFactor"):
            parameterNode.SetParameter("UseScaleFactor","false")
        if not parameterNode.GetParameter("LPSToRAS"):
            parameterNode.SetParameter("LPSToRAS","true")
            
   


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
