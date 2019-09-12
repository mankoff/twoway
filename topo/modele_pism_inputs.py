# Prepares inputs for a ModelE-PISM coupled run
#
# Eg: python3 ../topo/modele_pism_inputs.py --out e17 --pism ../pism/std-greenland/g20km_10ka.nc

import argparse
import subprocess
import contextlib, os
import re
import netCDF4
import collections
import numpy as np

@contextlib.contextmanager
def pushd(dir):
    curdir= os.getcwd()
    os.chdir(dir)
    try:
        yield
    finally:
        os.chdir(curdir)

def make_grid(grid_cmd, grid_fname):
    """Returns True if it ran grid creation command"""
    print('***************** {}'.format(grid_fname))
    if os.path.exists(grid_fname):
        return False

    cmd = grid_cmd + ['-o', grid_fname]
    print(' '.join(cmd))
    ret = subprocess.run(cmd)
    if ret != 0:
        raise RuntimError("Command failed: {}".format(cmd))
    return True


makefile_str = """
# Recipe for generating TOPO files from PISM state files.
# This Makefile is machine-generated by modele_pism_inputs.py

all : topoa.nc

# ----------------- Things we make here
{gridA} {global_ecO_ng} {topoo_ng} :
	cd {topo_root}; $(MAKE) {gridA_leaf} {global_ecO_ng_leaf} {topoo_ng_leaf}


{gridI} : # only re-generate if it doesn't exist, it is named by content
	spec_to_grid gridI_spec.nc -o {gridI}   # gridI_spec.nc was generated from PISM state file

{exgrid} : {gridI} {gridA}
	overlap {gridA} {gridI} -o {exgrid}

# Just for kicks
gridI.nc : {gridI}
	ln -s {gridI} gridI.nc
exgridO.nc : {exgrid}
	ln -s {exgrid} exgridO.nc


gcmO.nc : {exgrid} {pism_state} {gridA} {gridI}
	echo '*****************************************************************'
	echo '[makefile] Assembling IceBin Input File from grids (contains loadable gcmO).'
	python3 {topo_root}/write_icebin_in_base.py {gridA} {gridI} {exgrid} {pism_state} ./gcmO.nc

topoo_merged.nc : {pism_state} gcmO.nc {global_ecO_ng} {topoo_ng}
        # Merge without squashing
	make_merged_topoo --squash_ec 0 --topoo_merged topoo_merged.nc --elevmask pism:{pism_state} --gcmO gcmO.nc --global_ecO {global_ecO_ng} --topoo {topoo_ng}
        # Merge with squashing
	# make_merged_topoo --topoo_merged topoo_merged.nc --elevmask pism:{pism_state} --gcmO gcmO.nc --global_ecO {global_ecO_ng} --topoo {topoo_ng}


topo_oc.nc : topoo_merged.nc
	python3 {topo_root}/make_topo_oc.py topoo_merged.nc -o topo_oc.nc

topoa_nc4.nc : topoo_merged.nc
	make_topoa -o topoa_nc4.nc --global_ecO topoo_merged.nc --topoo topoo_merged.nc 2>topoa_nc4.err

topoa.nc : topoa_nc4.nc
	nccopy -k classic topoa_nc4.nc topoa.nc
"""


# IceBin-specific rundeck extension...
icebin_cdl_str = """
// Sample Icebin parameter file.  Copy to [rundir]/config/icebin.cdl
//
// See also the following rundeck paramters to control the Stieglitz snow/firn model:
// (LISnowParams.F90`` for documentation)
//      lisnow_target_depth
//      lisnow_rho_fresh_snow
//      lisnow_rho_snow_firn_cutoff
//      lisnow_max_fract_water
//      lisnow_epsilon
//      lisnow_min_snow_thickness
//      lisnow_min_fract_cover
//      lisnow_dump_forcing
//      lisnow_percolate_nl

netcdf icebin {{
variables:
    // Setup methods (in ectl) to be run after symlinks are
    // created and before ModelE is launched.
    // Names of these attributes can be whatever you like
    int setups ;
        setups:landice = "ectl.xsetup.pism_landice.xsetup";

    // ModelE-specific variables cover all ice sheets
    int m.info ;

        m.info:grid = "input-file:./input/gcmO.nc";

        // Where IceBin may write stuff
        m.info:output_dir = "output-dir:icebin";

        // Normally, set use_smb="t"
        // FOR TESTING ONLY: set to "f" and IceBin will pass a zero SMB and
        // appropriately zero B.C. to the ice sheet.
        m.info:use_smb = "t" ;

    // Additional variables agument m.greenland.info from main icebin_in
    // These variables are specific to Greenland
    int m.greenland.info ;
        // Output for greenland-specific stuff
        m.greenland.info:output_dir = "output-dir:greenland";

        // The ice model with which we are coupling.
        // See IceCoupler::Type [DISMAL, PISM, ISSM, WRITER]
        m.greenland.info:ice_coupler = "PISM" ;

        // Should we upate the elevation field in update_ice_sheet()?
        // Normally, yes.  But in some TEST CASES ONLY --- when the SMB
        // field was created with a different set of elevations than the
        // ice model is using --- then this can cause problems in the
        // generated SMB fields.
        // See IceModel_PISM::update_elevation
        m.greenland.info:update_elevation = "t" ;

        // Variable currently in icebin_in, but maybe they should be moved here.
        // m.greenland.info:interp_grid = "EXCH" ;
        // m.greenland.info:interp_style = "Z_INTERP" ;
        // Also: hcdefs, indexingHC

    // Variables specific to the ModelE side of the coupling
    double m.greenland.modele ;

        // Should ModelE prepare for Dirichlet or Neumann boundary
        // conditions with the dynamic ice model?
        // See 
        m.greenland.modele:coupling_type = "DIRICHLET_BC" ;

    double m.greenland.pism ;
        // Command-line arguments provided to PISM upon initialization
        // Paths will be resolved for filenames in this list.
{greenland_pism_args}

#        m.greenland.pism:i = "input-file:pism/std-greenland/g20km_10ka.nc" ;
#        m.greenland.pism:skip = "" ;
#        m.greenland.pism:skip_max = "10" ;
#        m.greenland.pism:surface = "given" ;
#        m.greenland.pism:surface_given_file = "input-file:pism/std-greenland/pism_Greenland_5km_v1.1.nc" ;
#        m.greenland.pism:calving = "ocean_kill" ;
#        m.greenland.pism:ocean_kill_file = "input-file:pism/std-greenland/pism_Greenland_5km_v1.1.nc" ;
#        m.greenland.pism:sia_e = "3.0" ;
#        m.greenland.pism:ts_file = "output-file:greenland/ts_g20km_10ka_run2.nc" ;
#        m.greenland.pism:ts_times = "0:1:1000" ;
#        m.greenland.pism:extra_file = "output-file:greenland/ex_g20km_10ka_run2.nc" ;
#        m.greenland.pism:extra_times = "0:.1:1000" ;
#        m.greenland.pism:extra_vars = "climatic_mass_balance,ice_surface_temp,diffusivity,temppabase,tempicethk_basal,bmelt,tillwat,csurf,mask,thk,topg,usurf" ;
#        m.greenland.pism:o = "g20km_10ka_run2.nc" ;

}}
"""

def snoop_pism(pism_state):
    """Snoops around a PISM run directory, looking for key files and
    strings needed to set up IceBin.
    pism_state:
        Name of the PISM state file
    """
    # Directory of the PISM run
    pism_state = os.path.realpath(pism_state)
    pism_dir = os.path.split(pism_state)[0]

    # Read the main PISM state file
    vals = collections.OrderedDict()
    with netCDF4.Dataset(pism_state) as nc:
        # Read command line
        cmd = re.split(r'\s+', nc.command)
        config_nc = nc.variables['pism_config']
        Mx = int(getattr(config_nc, 'grid.Mx'))
        My = int(getattr(config_nc, 'grid.My'))
        vals['grid.Mx'] = Mx
        vals['grid.My'] = My

    # Parse command line into (name, value pairs)
    args = collections.OrderedDict()
    vals['args'] = args
    i = 0
    while i < len(cmd):
        if cmd[i].startswith('-'):
            if (not cmd[i+1].startswith('-')) or (len(cmd[i+1])>1 and cmd[i+1][2].isdigit()):
                args[cmd[i][1:]] = cmd[i+1]
                i += 1
            else:
                args[cmd[i][1:]] = None
        i += 1

    # Read the 'i' file for more info
    fname = os.path.normpath(os.path.join(pism_dir, args['i']))
    with netCDF4.Dataset(fname) as nc:
        vals['proj4'] = nc.proj4
        xc5 = nc.variables['x1'][:]    # Cell centers (for standard 5km grid)
        yc5 = nc.variables['y1'][:]

    # Determine cell centers on our chosen resolution
    xc = np.array(list(xc5[0] + (xc5[-1]-xc5[0]) * ix / (Mx-1) for ix in range(0,Mx)))
    yc = np.array(list(yc5[0] + (yc5[-1]-yc5[0]) * iy / (My-1) for iy in range(0,My)))
    vals['x_centers'] = xc
    vals['y_centers'] = yc
    #vals['index_order'] = (0,1)    # PISM order
    vals['index_order'] = (1,0)    # SeaRise order

    # Name grid after name of input file
    idx = int(.5 + (xc[1] - xc[0]) / 1000.)
    idy = int(.5 + (yc[1] - yc[0]) / 1000.)
    if idx == idy:
        dxdy = '{}'.format(idx)
    else:
        dxdy = '{}_{}'.format(idx,idy)

    iname = os.path.split(args['i'])[1]
    if iname.startswith('pism_Greenland'):
        vals['name'] = 'pism_g{}km_{}{}'.format(dxdy, vals['index_order'][0], vals['index_order'][1])
    else:
        vals['name'] = '{}{}km_{}'.format(os.path.splitext(iname)[0], dxdy, vals['index_order'][0], vals['index_order'][1])

    return vals

def make_pism_args(pism_dir, pism):
    """Generates a (key, value) list of PISM arguments for the config file we will write,
    BASED ON the PISM arguments of the original bootstrap

    pism:
        Result of snoop_pism()
    """
    args = collections.OrderedDict(pism['args'].items())
    for arg in ('bootstrap', 'Mx', 'My', 'Mz', 'Mbz', 'z_spacing', 'Lz', 'Lbz',
        'ys', 'ye',   # Model run duration
        ):
        try:
            del args[arg]
        except KeyError:
            pass

    # Get absolute name of files given in PISM command line as relative
    #for key in ('i', 'surface_given_file', 'ocean_kill_file', 'ts_file', 'extra_file', 'o'):
    for key in ('i', 'surface_given_file', 'ocean_kill_file'):
        args[key] = os.path.normpath(os.path.join(pism_dir, args[key]))

    # Add to -extra_vars
    extra_vars = args['extra_vars'].split(',')
    evset = set(extra_vars)
    for var in "climatic_mass_balance,ice_surface_temp,diffusivity,temppabase,tempicethk_basal,bmelt,tillwat,csurf,mask,thk,topg,usurf".split(','):
        if var not in evset:
            extra_vars.append(var)
    args['extra_vars'] = ','.join(extra_vars)

    return args


def center_to_boundaries(xc):
    xb = np.zeros(len(xc)+1)
    xb[0] = 1.5*xc[0]-.5*xc[1]
    xb[1:-1] = (xc[0:-1] + xc[1:]) * .5
    xb[-1] = 1.5*xc[-1]-.5*xc[-2]
    return xb

def write_gridspec_xy(pism, spec_fname):
    """Given info gleaned from PISM, writes it out as a GridSpec_XY that
    can be read by the grid generator."""

    with netCDF4.Dataset(spec_fname, 'w') as nc:
        xc = pism['x_centers']
        xb = center_to_boundaries(xc)
        nc.createDimension('grid.x_boundaries.length', len(xb))
        nc_xb = nc.createVariable('grid.x_boundaries', 'd', ('grid.x_boundaries.length'))
        nc_xb[:] = xb

        yc = pism['y_centers']
        yb = center_to_boundaries(yc)
        nc.createDimension('grid.y_boundaries.length', len(yb))
        nc_yb = nc.createVariable('grid.y_boundaries', 'd', ('grid.y_boundaries.length'))
        nc_yb[:] = yb

        nc_info = nc.createVariable('grid.info', 'i', ())
        nc_info.setncattr('name', pism['name'])
        nc_info.type = 'XY'
        nc_info.indices = pism['index_order']    # Old PISM indexing order; reverse for new PISM / SeaRISE
        nc_info.sproj = pism['proj4']
        nc_info.nx = len(xc)
        nc_info.ny = len(yc)


def modele_pism_inputs(topo_root, coupled_dir, pism_state,
    grid_dir=None):

    """twoway_root:
        Root of the checked-out *twoway* git project / topo.  Eg: $HOME/git/twoway/topo
    coupled_dir: (OUT)
        Name of directory where intermediate files for coupled run
        inputs are written.
    gridI_cmd:  [...]
        Command line that, when run, produces the PISM grid
        NOTE: '-o <outfile.nc>' will be appended to this command line
    gridI_leaf: (OUT)
        Name of output file in which to write the PISM grid
        (leafname only, no directory)
    grid_dir: (OUT)
        Place to look for pre-generated grids (and overlaps)
    """
    pism_dir = os.path.split(pism_state)[0]

    if grid_dir is None:
        grid_dir = topo_root
    os.makedirs(grid_dir, exist_ok=True)
    os.makedirs(coupled_dir, exist_ok=True)

    # Create ModelE grid and other general stuff (not PISM-specific)
    gridA_leaf = 'modele_ll_g1qx1.nc'
    repl = dict(    # Used to create templated makefile
        pism_state = pism_state,
        topo_root = topo_root,

        gridA = os.path.join(topo_root, gridA_leaf),
        global_ecO_ng = os.path.join(topo_root, 'global_ecO_ng.nc'),
        topoo_ng = os.path.join(topo_root, 'topoo_ng.nc'),

        gridA_leaf = gridA_leaf,
        global_ecO_ng_leaf = 'global_ecO_ng.nc',
        topoo_ng_leaf = 'topoo_ng.nc')


    # Create the PISM grid spec
    pism = snoop_pism(pism_state)
    write_gridspec_xy(pism, os.path.join(coupled_dir, 'gridI_spec.nc'))
    gridI_leaf = '{}.nc'.format(pism['name'])
#    gridI_leaf = 'sr_g20_pism.nc'
#    gridI_leaf = 'sr_g20_searise.nc'
    gridI_fname = os.path.join(grid_dir, gridI_leaf)
    repl['gridI'] = gridI_fname

    # Overlap the two
    exgrid_leaf = '{}-{}'.format(os.path.splitext(gridA_leaf)[0], gridI_leaf)
    repl['exgrid'] = os.path.join(grid_dir, exgrid_leaf)

    # Do the rest
    print('************** Makefile')
    with pushd(coupled_dir):
        args = make_pism_args(pism_dir, pism)
        lines = []
        for key,val in args.items():
            lines.append('        m.greenland.pism:{} = "{}" ;'.format(key,val))
        repl['greenland_pism_args'] = '\n'.join(lines)

        with open('icebin.cdl', 'w') as fout:
            fout.write(icebin_cdl_str.format(**repl))

        with open('modele_pism_inputs.mk', 'w') as fout:
            fout.write(makefile_str.format(**repl))
        cmd = ['make', '-f', 'modele_pism_inputs.mk', 'topoa.nc', 'topo_oc.nc']
        print(' '.join(cmd))
        subprocess.run(cmd)

def main():
    topo_root = os.path.split(os.path.realpath(__file__))[0]

    parser = argparse.ArgumentParser(description='Set up input files for a Coupled ModelE - PISM run')

    parser.add_argument('--pism', dest='pism',
        required=True,
        help='PISM state file (eg after spinup)')
    parser.add_argument('--out', dest='coupled_dir',
        required=True,
        help="Name of directory for output files.  Eg: <ectl-run>/inputs")
    args = parser.parse_args()

    pism = snoop_pism(args.pism)
    write_gridspec_xy(pism, 'x.nc')

    for k,v in pism['args'].items():
        if k != 'args':
            print(k,v)

    modele_pism_inputs(topo_root, os.path.realpath(args.coupled_dir), os.path.realpath(args.pism),
        grid_dir=topo_root)

main()

