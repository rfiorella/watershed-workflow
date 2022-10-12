# Genral packages to import ----------------------------------------------
from distutils.command.install_egg_info import to_filename
import os,sys
import numpy as np
from matplotlib import pyplot as plt
from matplotlib import cm as pcm
import shapely
import logging
import pandas
import copy
import time
from scipy import integrate
import pickle
import rasterio
import fiona
pandas.options.display.max_columns = None

import requests
import py7zr
import urllib
import ssl

# watershed_workflow packages and modules to import ----------------------------------------------
import watershed_workflow
import watershed_workflow.source_list
import watershed_workflow.ui
import watershed_workflow.colors
import watershed_workflow.condition
import watershed_workflow.mesh
import watershed_workflow.split_hucs
import watershed_workflow.create_river_mesh
import watershed_workflow.densify_rivers_hucs
import watershed_workflow.daymet

# Change working directory and import watershed analysis functions ---------------
os.chdir('/Users/8n8/Documents/myRepos/watershed-workflow/examples/rnTools')
from watershed_analysis_functions import *
from daymet_watershed_analysis_functions import *

# Test the watershed analysis routines

huc = '060102070302' # This is the huc 12-digit Hydrologic Unit for East Fork Poplar Creek

# Basic information for the coordinate reference system and data sources for watershed_workflow -------------

## Coordinate reference system
crs = watershed_workflow.crs.daymet_crs()
## Dictionary of source objects
sources = watershed_workflow.source_list.get_default_sources()
sources['hydrography'] = watershed_workflow.source_list.hydrography_sources['NHD Plus']
sources['HUC'] = watershed_workflow.source_list.huc_sources['NHD Plus']
sources['DEM'] = watershed_workflow.source_list.dem_sources['NED 1/3 arc-second']
watershed_workflow.source_list.log_sources(sources)

#  Read the watershed boundary ----------------------------------------

profile_ws, ws = watershed_workflow.get_huc(sources['HUC'], huc, crs)
watershed = watershed_workflow.split_hucs.SplitHUCs([ws])

fig, axs = plt.subplots(1,1,figsize=[10,10])
watershed_workflow.plot.hucs(watershed, crs, 'k', axs)
plt.show()



##################

# Step 1: Get the bounds from the HUC
watersheds_shapely = list(watershed.polygons())
bounds = watersheds_shapely[0].bounds
bounds_crs = profile_ws 

'''
NHDPlusV2 data is distributed by the major "Drainage Areas" of the United States.
Within a Drainage Area, the NHDPlusV2 data components are packaged into compressed 
files either by Vector Processing Unit (VPU) or Raster Processing Unit (RPU).
In NHDPlusV2, the processing units are referred to as “Vector Processing Unit (VPU)” for
vector data and “Raster Processing Unit (RPU)” for raster data. RPUs are used for the raster 
components (elevation, flow direction and flow accumulation grids) and the VPUs are used 
for all vector feature classes and all tables. 
'''

# Global data provided by NHDPlusV2
# https://www.epa.gov/waterdata/nhdplus-global-data

path_BoundaryUnitsNHDPlusV21 = "/Users/8n8/Library/CloudStorage/OneDrive-OakRidgeNationalLaboratory/ornl/01_projects/01_active/IDEAS/data/gis_data/nhd_plusv21/NHDPlusGlobalData"
filename_BoundaryUnitsNHDPlusV21 = "BoundaryUnit.shp"

downloadfile = os.path.join(path_BoundaryUnitsNHDPlusV21, filename_BoundaryUnitsNHDPlusV21)
with fiona.open(downloadfile) as fid:
    # Get the CRS for the Boundary Units
    BoundaryUnits_crs = watershed_workflow.crs.from_fiona(fid.profile['crs'])
    # Project the watershed boundary to the CRS for the Boundary Units
    bounds = watershed_workflow.warp.bounds(
        bounds, bounds_crs, BoundaryUnits_crs) 
    # Get the boundary Units that intersect with the watershed 
    BUs = [r for (i, r) in fid.items(bbox=bounds)]

# Consolidate information from the selected Boundary Units
UnitType = []
UnitID = []
DrainageID = []
for pp in BUs:
    UnitType.append(pp['properties']['UnitType'])    
    UnitID.append(pp['properties']['UnitID']) 
    DrainageID.append(pp['properties']['DrainageID'])

UnitType = np.array(UnitType)
UnitID = np.array(UnitID)
DrainageID = np.array(DrainageID)

# Find tuples of Drainage Areas, VPUs, and RPUs
daID_vpu_rpu = [] # list of lists with the Drainage Areas, VPUs, and RPUs
daID_unique = np.unique(DrainageID)

for dd in daID_unique:

    vpu_unique = np.unique(UnitID[np.argwhere((UnitType == 'VPU') & (DrainageID == dd))])
    
    for vv in vpu_unique:
        daID_vpu_rpu += [[dd, vv, UnitID[ii]] for ii in range(len(UnitType)) \
            if (('RPU' in UnitType[ii]) & (vv[0:2] in UnitID[ii]))]

# File names to download


component_name = ['']
version_component = ['']

for kk, vars in enumerate(daID_vpu_rpu):
# "NHDPlusV21_" + vars[0] + "_" + vars[1] + "_" + component_name + "_" + version_component
# "NHDPlusV21_" + vars[0] + "_" + vars[1] + "_" + vars[2] + "_" + component_name + "_" + version_component

# Create folder named:
folder_name = "NHDPlus" + dID_vpu_rpu[kk][1]

# RPU components
"NHDPlusV21_" + vars[0] + "_" + vars[1] + "_" + vars[2] + "_" + component_name + "_" + version_component
    # CatSeed_02 -- 01, 02 
    # FdrFac_02 -- 01, 03, 
    # FdrNull_02 -- 01, 03
    # HydroDem_02 -- 01, 02
    # NEDSnapshot_03 -- 01, 03

# VPU-Wide components
"NHDPlusV21_" + vars[0] + "_" + vars[1] + "_" + component_name + "_" + version_component
    # EROMExtension_07 -- 05, 06, 07, 11, 
    # NHDPlusAttributes_10 -- 07, 09, 10, 14, 
    # NHDPlusBurnComponents_05 -- 02, 03, 05, 07, 
    # NHDPlusCatchment_02 -- 01, 05
    # NHDSnapshotFGDB_07 -- 04, 06, 07, 08, 09 
    # NHDSnapshot_07 -- 04, 06, 07, 08, 09
    # VPUAttributeExtension_05 -- 03, 04, 05, 07
    # VogelExtension_02 -- 01, 04, 06
    # WBDSnapshot_04 -- 03, 04, 06



theURL = 'https://edap-ow-data-commons.s3.amazonaws.com/NHDPlusV21/Data/NHDPlusMS/NHDPlus06/NHDPlusV21_MS_06_NHDPlusAttributes_10.7z'
# Download the data behind the URL
response = requests.get(theURL)
status_code = response.status_code # A status code of 200 means it was accepted


theURL = 'https://www.epa.gov/waterdata/nhdplus-tennessee-data-vector-processing-unit-06'
req = urllib.request.Request(theURL)
gcontext = ssl.SSLContext()  # To bypass the certificate issues "urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate in certificate chain (_ssl.c:997)>"
html = str(urllib.request.urlopen(req, context=gcontext).read())
html.find('NHDPlusAttributes')
html[28728-10:28728+10]




pathDataOut = '/Users/8n8/Downloads/testDownloadNHDPlusV2'
filename_out = os.path.join(pathDataOut, theURL.split('/')[-1])
open(filename_out, "wb").write(response.content)

# Unzip file
with py7zr.SevenZipFile(filename_out, 'r') as archive:
    archive.extractall(path=pathDataOut)



        # cwd = os.getcwd()
        # try:
        #     os.chdir(to_location)
        #     libarchive.extract_file(filename)

# https://edap-ow-data-commons.s3.amazonaws.com/NHDPlusV21/Data/NHDPlusMS/NHDPlus10U/NHDPlusV21_MS_10U_EROMExtension_07.7z
# https://edap-ow-data-commons.s3.amazonaws.com/NHDPlusV21/Data/NHDPlusGB/NHDPlusV21_GB_16_EROMExtension_04.7z
# https://edap-ow-data-commons.s3.amazonaws.com/NHDPlusV21/Data/NHDPlusGB/NHDPlusV21_GB_16_EROMExtension_04.7z