import logging
import os
from typing import Annotated, Optional
import pathlib
import vtk
import numpy as np
import re

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# LoadContourFile
#


class LoadContourFile(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("LoadContourFile")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = ["LabUtils"]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["S. Korteland, Dept of Biomedical Engineering, Erasmus MC, Rotterdam, The Netherlands "]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This module can be used to load contours stored in a .ctr file generated in QCU.
See more information in <a href="https://github.com/organization/projectname#LoadContourFile">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
""")


#
# LoadContourFileParameterNode
#


@parameterNodeWrapper
class LoadContourFileParameterNode:
    """
    The parameters needed by module.

    inputFile - path to the contour file to be loaded
    convertToMM - convert the contour data to millimeter using the scaling specified in the contour file (True/False)
    LPSToRAS - convert from LPS coordinate system to RAS coordinate system used in 3D slicer (True/False)
    """

    inputFile: pathlib.Path
    convertToMM: bool
    LPSToRAS: bool


#
# LoadContourFileWidget
#


class LoadContourFileWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/LoadContourFile.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = LoadContourFileLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.loadButton.connect("clicked(bool)", self.onLoadButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanLoad)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        
    def setParameterNode(self, inputParameterNode: Optional[LoadContourFileParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanLoad)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanLoad)
            self._checkCanLoad()

    def _checkCanLoad(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputFile:
            self.ui.loadButton.toolTip = _("Load contour file")
            self.ui.loadButton.enabled = True
            self.ui.convertToMMCheckBox.enabled = True
            self.ui.LPSToRASCheckBox.enabled = True
        else:
            self.ui.loadButton.toolTip = _("Select file to load")
            self.ui.loadButton.enabled = False
            self.ui.convertToMMCheckBox.enabled = False
            self.ui.LPSToRASCheckBox.enabled = False

    def onLoadButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to load file."), waitCursor=True):
            # Compute output
            contoursPolyData = self.logic.loadContourFile(self._parameterNode.inputFile, self._parameterNode.convertToMM, self._parameterNode.LPSToRAS)

            # To node
            # create slicer segment node from contour points
            # based on https://discourse.slicer.org/t/programmatically-create-a-segmentationnode-and-labelmapnode-from-polygon-coordinates/8448/4
            # Create segmentation node where we will store segments
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            segmentationNode.CreateDefaultDisplayNodes()
            #segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode('')
            segmentation = segmentationNode.GetSegmentation()
            segmentation.SetSourceRepresentationName(slicer.vtkSegmentationConverter.GetPlanarContourRepresentationName())

            segment = slicer.vtkSegment()
            segmentName = os.path.splitext(os.path.basename(self._parameterNode.inputFile))[0]
            segment.SetName(segmentName)
            #segment.SetColor([25/255, 115/255, 175/255])
            # note: to have the Planar contour representation visible in the segmentation module, and have the possibility to convert 
            # to other representations (binary label map, closed surface etc) make sure the SlicerRT extension is installed.
            segment.AddRepresentation(slicer.vtkSegmentationConverter.GetPlanarContourRepresentationName(), contoursPolyData)
            segmentation.AddSegment(segment)
            
            # also create Ribbon model for better display in 2D
            segmentation.CreateRepresentation("Ribbon model")
        
            # set preferred display
            segmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName2D('Ribbon model')



#
# LoadContourFileLogic
#


class LoadContourFileLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return LoadContourFileParameterNode(super().getParameterNode())

    def loadContourFile(self,
                inputFile: str,
                convertToMM: bool,
                LPSToRAS: bool) -> None:
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputFile: file to be loaded
        """
        print('In loadContourFile')
        if not inputFile:
            raise ValueError("Input file is invalid")

  
        # Load header data
        with open(inputFile,'r') as file:
            headerLine0 = file.readline()
            # get the numbers from the first header string
            patternToFindNumbers = r"[-+]?\d*\.\d+|\d+"
            header0Numbers= re.findall(patternToFindNumbers, headerLine0)
            # scalefactor is the first number in the first header line
            scaleFactor = float(header0Numbers[0])

            headerLine1 = file.readline()
            header1Numbers = re.findall(patternToFindNumbers, headerLine1)
            # imagecenter are the numbers in the second header line
            imgCenter = np.array((float(header1Numbers[0]), float(header1Numbers[1])))

        # read in the contour data
        contourData = np.genfromtxt(inputFile,skip_header=2)

        # reorder framenr,x,y
        contourData = contourData[:,[1,2,0]]

        # reorder to RAS
        if LPSToRAS:
            contourData[:,0] = -contourData[:,0]
            contourData[:,1] = -contourData[:,1]

        # convert contour number from contour file to IVUS frame number
        # TODO: this will be different per case so let user define
        IVUSStartFrame = 0
        IVUSStep = 1
        contourData[:,2] = IVUSStartFrame+ contourData[:,2] * IVUSStep;

        # if scaling from pixel to mm apply scaleFactor
        if convertToMM:
            contourData[:,:2] = contourData[:,:2]*scaleFactor

        # only keep unique entries, sometimes points are duplicated
        # get the indexes of the rows for sorted unique array
        rowIndexes = np.unique(contourData, return_index=True, axis=0)[1]
        contourDataUnique = contourData[np.sort(rowIndexes)]

        # reshape
        dataPointTotal = contourDataUnique.shape[0]
        framesTotal = np.unique(contourData[:,2]).shape[0]
        dataPointPerFrame=int(dataPointTotal/framesTotal)

        contourDataReshape = np.reshape(contourDataUnique,(framesTotal,dataPointPerFrame,-1))


        # Create a segment from planar contours - can be repeated for multiple segments
        contoursPolyData = vtk.vtkPolyData()
        contourPoints = vtk.vtkPoints()
        contourLines = vtk.vtkCellArray()
        contoursPolyData.SetLines(contourLines)
        contoursPolyData.SetPoints(contourPoints)
        for contour in contourDataReshape:
            startPointIndex = contourPoints.GetNumberOfPoints()
            contourLine = vtk.vtkPolyLine()
            linePointIds = contourLine.GetPointIds()
            for point in contour:
                linePointIds.InsertNextId(contourPoints.InsertNextPoint(point))
            linePointIds.InsertNextId(startPointIndex) # make the contour line closed
            contourLines.InsertNextCell(contourLine)

        return contoursPolyData

#
# LoadContourFileTest
#


class LoadContourFileTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_LoadContourFile1()

    def test_LoadContourFile1(self):
        """Ideally you should have several levels of tests.  At the lowest level
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


        self.delayDisplay("Test passed")
