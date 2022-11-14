from requests_html import HTMLSession
import fiona
import os
import watershed_workflow
import watershed_workflow.sources.utils as source_utils
import numpy as np
import logging
import shutil
import py7zr
# import re

def get_watershed_boundaries(hucs, sources, crs):

    #  Read the watershed boundary ----------------------------------------
    my_hucs = []
    my_hucs_profile = []
    for huc in hucs:
        profile_ws, ws = watershed_workflow.get_huc(sources['HUC'], huc, crs)
        my_hucs.append(ws)
        my_hucs_profile.append(profile_ws)
    watershed = watershed_workflow.split_hucs.SplitHUCs(my_hucs) # This is a collection of subwatersheds

    # Get the bounds from the HUC ----------------------------------------
    bounds = watershed.exterior().bounds # (minx, miny, maxx, maxy)
    bounds_crs = my_hucs_profile[0]

    return watershed, bounds, bounds_crs

def get_NHDPlusV2_URLs_from_EPA_url(url, verify=True):

    with HTMLSession() as session:
        response = session.get(url, verify=verify)
        response.raise_for_status()
        status_code = response.status_code  # A status code of 200 means it was accepted
        print("Status code:" + str(status_code))
        html = response.html
        html.render()
        all_links = html.absolute_links

    return [ll for ll in list(all_links) if ".7z" in ll]
    
def get_NHDPlusV2_component_url(data_links, componentnames): 
    return [get_url_NHD_dataset(data_links, cc)[0] for cc  in componentnames]

def get_url_NHD_dataset(data_links, nhd_name):
    return [match for match in data_links if nhd_name in match]

def get_BoundaryUnit_Info(bounds, bounds_crs, BoundaryUnitFile, enforce_VPUs = []):
    # bounds =  watershed bounds -- Returns a (minx, miny, maxx, maxy) tuple (float values) that bounds the object.
    # bounds_crs = CRS for the watershed bounds 
    # enforce_VPUs = list with the huc names

    '''
    NHDPlusV2 data is distributed by the major "Drainage Areas" of the United States.
    Within a Drainage Area, the NHDPlusV2 data components are packaged into compressed 
    files either by Vector Processing Unit (VPU) or Raster Processing Unit (RPU).
    In NHDPlusV2, the processing units are referred to as “Vector Processing Unit (VPU)” for
    vector data and “Raster Processing Unit (RPU)” for raster data. RPUs are used for the raster 
    components (elevation, flow direction and flow accumulation grids) and the VPUs are used 
    for all vector feature classes and all tables. 
    '''

    with fiona.open(BoundaryUnitFile) as fid:
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
    daID_vpu_rpu = []  # list of lists with the Drainage Areas, VPUs, and RPUs
    daID_unique = np.unique(DrainageID)

    for dd in daID_unique:

        vpu_unique = np.unique(
            UnitID[np.argwhere((UnitType == 'VPU') & (DrainageID == dd))])

        for vv in vpu_unique:
            daID_vpu_rpu += [[dd, vv, UnitID[ii]] for ii in range(len(UnitType))
                            if (('RPU' in UnitType[ii]) & (vv[0:2] in UnitID[ii]))]
    
    if enforce_VPUs:
        print("--------- Enforcing VPUs ---------")
        enforce_VPUs = np.unique([tt[0:2] for tt in enforce_VPUs])
        toKeep = np.zeros((1,len(daID_vpu_rpu)), dtype=bool)
        for vpu in enforce_VPUs:
            print(vpu)
            toKeep += [vpu in vv[1] for vv in daID_vpu_rpu]
        daID_vpu_rpu = [i for (i, v) in zip(daID_vpu_rpu, toKeep[0]) if v]

    return daID_vpu_rpu

def get_URLs_VPU(daID_vpu_rpu):

    vpu_info = {"01": {"url_name": "https://www.epa.gov/waterdata/nhdplus-northeast-data-vector-processing-unit-01", "vpu_name": "Northeast"},
    "02": {"url_name": "https://www.epa.gov/waterdata/nhdplus-mid-atlantic-data-vector-processing-unit-02", "vpu_name": "Mid Atlantic"},
    "03N": {"url_name": "https://www.epa.gov/waterdata/nhdplus-south-atlantic-north-data-vector-processing-unit-03n", "vpu_name": "South Atlantic North"},
    "03S": {"url_name": "https://www.epa.gov/waterdata/nhdplus-south-atlantic-south-data-vector-processing-unit-03s", "vpu_name": "South Atlantic South"},
    "03W": {"url_name": "https://www.epa.gov/waterdata/nhdplus-south-atlantic-west-data-vector-processing-unit-03w", "vpu_name": "South Atlantic West"},
    "04": {"url_name": "https://www.epa.gov/waterdata/nhdplus-great-lakes-data-vector-processing-unit-04", "vpu_name": "Great Lakes"},
    "05": {"url_name": "https://www.epa.gov/waterdata/nhdplus-ohio-data-vector-processing-unit-05", "vpu_name": "Ohio"},
    "06": {"url_name": "https://www.epa.gov/waterdata/nhdplus-tennessee-data-vector-processing-unit-06", "vpu_name": "Tennessee"},
    "07": {"url_name": "https://www.epa.gov/waterdata/nhdplus-upper-mississippi-data-vector-processing-unit-07", "vpu_name": "Upper Mississippi"},
    "08": {"url_name": "https://www.epa.gov/waterdata/nhdplus-lower-mississippi-data-vector-processing-unit-08", "vpu_name": "Lower Mississippi"},
    "09": {"url_name": "https://www.epa.gov/waterdata/nhdplus-souris-red-rainy-data-vector-processing-unit-09", "vpu_name": "Souris-Red-Rainy"},
    "10U": {"url_name": "https://www.epa.gov/waterdata/nhdplus-upper-missouri-data-vector-processing-unit-10u", "vpu_name": "Upper Missouri"},
    "10L": {"url_name": "https://www.epa.gov/waterdata/nhdplus-lower-missouri-data-vector-processing-unit-10l", "vpu_name": "Lower Missouri"},
    "11": {"url_name": "https://www.epa.gov/waterdata/nhdplus-ark-red-white-data-vector-processing-unit-11", "vpu_name": "Ark-Red-White"},
    "12": {"url_name": "https://www.epa.gov/waterdata/nhdplus-texas-data-vector-processing-unit-12", "vpu_name": "Texas"},
    "13": {"url_name": "https://www.epa.gov/waterdata/nhdplus-rio-grande-data-vector-processing-unit-13", "vpu_name": "Rio Grande"},
    "14": {"url_name": "https://www.epa.gov/waterdata/nhdplus-upper-colorado-data-vector-processing-unit-14", "vpu_name": "Upper Colorado"},
    "15": {"url_name": "https://www.epa.gov/waterdata/nhdplus-lower-colorado-data-vector-processing-unit-15", "vpu_name": "Lower Colorado"},
    "16": {"url_name": "https://www.epa.gov/waterdata/nhdplus-great-basin-data-vector-processing-unit-16", "vpu_name": "Great Basin"},
    "17": {"url_name": "https://www.epa.gov/waterdata/nhdplus-pacific-northwest-data-vector-processing-unit-17", "vpu_name": "Pacific Northwest"},
    "18": {"url_name": "https://www.epa.gov/waterdata/nhdplus-california-data-vector-processing-unit-18", "vpu_name": "California"},
    "20": {"url_name": "https://www.epa.gov/waterdata/nhdplus-hawaii-data-vector-processing-unit-20", "vpu_name": "Hawaii"},
    "21": {"url_name": "https://www.epa.gov/waterdata/nhdplus-puerto-rico-us-virgin-islands-data-vector-processing-unit-21", "vpu_name": "Puerto Rico/U.S. Virgin Islands"},
    "22A": {"url_name": "https://www.epa.gov/waterdata/nhdplus-american-samoa-data-vector-processing-unit-22a", "vpu_name": "American Samoa"},
    "22G": {"url_name": "https://www.epa.gov/waterdata/nhdplus-guam-data-vector-processing-unit-22g", "vpu_name": "Guam"},
    "22M": {"url_name": "https://www.epa.gov/waterdata/nhdplus-northern-mariana-islands-data-vector-processing-unit-22m", "vpu_name": "Northern Mariana Islands"}}

    return [vpu_info[tmp[1]]['url_name'] for tmp in daID_vpu_rpu]


def download_NHDPlusV2_datasets(data_dir, componentnames_vpu_wide, componentnames_rpu_wide, \
    bounds, bounds_crs, BoundaryUnitFile, enforce_VPUs = [], force=False):

    # Get the boundary Units that intersect with the watershed

    daID_vpu_rpu = get_BoundaryUnit_Info(bounds, bounds_crs,BoundaryUnitFile, enforce_VPUs=enforce_VPUs)
    
    print('Tiles needed: ' )
    print(daID_vpu_rpu)
    print('------------------------------')
    
    # Get the base URLs
    URLs = get_URLs_VPU(daID_vpu_rpu)

    # for each URL 
    for kk in range(len(daID_vpu_rpu)):

        data_links = get_NHDPlusV2_URLs_from_EPA_url(URLs[kk], verify=False)
        url_vpu_wide = get_NHDPlusV2_component_url(data_links, componentnames_vpu_wide)
        url_rpu_wide = get_NHDPlusV2_component_url(data_links, componentnames_rpu_wide)
        daID, vpu, rpu = daID_vpu_rpu[kk]
        
        # Download the data

        filenames = []
        for cc in range(len(componentnames_vpu_wide)):    
            url = url_vpu_wide[cc]
            filenames.append(
                download_NHDPlusV2_datasets_component(url, data_dir, vpu, force=force)
            )
        for cc in range(len(componentnames_rpu_wide)):    
            url = url_rpu_wide[cc]
            filenames.append(
                download_NHDPlusV2_datasets_component(url, data_dir, vpu, force=force)
            )
    return daID_vpu_rpu, filenames 



def download_NHDPlusV2_datasets_component(url, data_dir, vpu, force=False):

    """Find and download data from a given HUC.

    Parameters
    ----------
    url : str
        URL for the dataset
    data_dir : str 
        General path where all the datasets are stored
    vpu : str
        Vector Processing Unit fot the dataset    
    force : bool, optional
        If true, re-download even if a file already exists.

    Returns
    -------
    download_folder : str
        The path to the resulting downloaded dataset.
    """
    # check directory structure
    download_folder = os.path.join(data_dir,'hydrography',('NHDPlus'+str(vpu)))
    path_raw = os.path.join(download_folder,'raw')
    path_unziped = os.path.join(download_folder,'unziped')
    
    os.makedirs(download_folder, exist_ok=True)
    os.makedirs(path_raw, exist_ok=True)
    os.makedirs(path_unziped, exist_ok=True)

    filename = os.path.join(path_raw,url.split("/")[-1])
    if (not os.path.exists(filename)) or force:

        logging.info("Attempting to download source for target '%s'" % filename)
        source_utils.download(url, filename, force)
        # Unzip file
        with py7zr.SevenZipFile(filename, 'r') as zip:
            targets = zip.getnames()
            zip.extract(path=path_unziped, targets=targets)
        
        nested_targets = [tt for tt in targets if len(tt.split('/')) >= 3] 
        path_from = os.path.join(path_unziped,'/'.join(nested_targets[0].split('/')[0:3]))

        shutil.move(path_from,download_folder)
        shutil.rmtree(path_unziped)

    else:
        shutil.rmtree(path_unziped)
        logging.info("Source for target '%s' already exist" % filename)
        with py7zr.SevenZipFile(filename, 'r') as zip:
            targets = zip.getnames()
        
        nested_targets = [tt for tt in targets if len(tt.split('/')) >= 3] 
        path_from = os.path.join(path_unziped,'/'.join(nested_targets[0].split('/')[0:3]))

    return os.path.join(download_folder, path_from.split('/')[-1])    

    

    # download_folder = os.path.join(data_dir,'hydrography',('NHDPlus'+str(vpu)),component_name)
    # path_raw = os.path.join(download_folder,'raw')
    # path_unziped = os.path.join(download_folder,'unziped')

    # os.makedirs(download_folder, exist_ok=True)
    # os.makedirs(path_raw, exist_ok=True)
    # os.makedirs(path_unziped, exist_ok=True)

    # filename = os.path.join(path_raw,url.split("/")[-1])
    # if not os.path.exists(filename) or force:

    #     logging.info("Attempting to download source for target '%s'" % filename)
    #     source_utils.download(url, filename, force)

    #     # Unzip file
    #     with py7zr.SevenZipFile(filename, 'r') as zip:
    #         targets = zip.getnames()
    #         zip.extract(path=path_unziped, targets=targets)

    #     nested_targets = [tt for tt in targets if len(tt.split('/')) >= 3] 
    #     path_from = os.path.join(path_unziped,'/'.join(nested_targets[0].split('/')[0:3]))

    #     shutil.move(path_from,download_folder)

    #     allfiles = [tt for tt in targets if os.path.isfile(os.path.join(path_unziped,tt))]
    #     alldirs = [tt for tt in targets if os.path.isdir(os.path.join(path_unziped,tt))]

    #     _ = [shutil.move(os.path.join(path_unziped,ff), os.path.join(download_folder,ff.split('/')[-1])) for ff in allfiles]
    #     shutil.rmtree(path_unziped)
#     return download_folder