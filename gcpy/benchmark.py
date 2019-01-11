""" Specific utilities re-factored from the benchmarking utilities. """

import os
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

import matplotlib as mpl
from matplotlib import ticker
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import ListedColormap

from cartopy import crs
from cartopy.mpl.geoaxes import GeoAxes  # for assertion

from PyPDF2 import PdfFileWriter, PdfFileReader

from .plot import WhGrYlRd, add_latlon_ticks
from .grid.horiz import make_grid_LL, make_grid_CS
from .grid.regrid import make_regridder_C2L
from .grid.regrid import make_regridder_L2L

# change default fontsize (globally)
# http://matplotlib.org/users/customizing.html
#mpl.rcParams['font.size'] = 12
#mpl.rcParams['axes.titlesize'] = 20

cmap_abs = WhGrYlRd  # for plotting absolute magnitude
cmap_diff = 'RdBu_r'  # for plotting difference


def plot_layer(dr, ax, title='', unit='', diff=False):
    '''Plot 2D DataArray as a lat-lon layer

    Parameters
    ----------
    dr : xarray.DataArray
        Dimension should be [lat, lon]

    ax : Cartopy GeoAxes object with PlateCarree projection
        Axis on which to plot this figure

    title : string, optional
        Title of the figure

    unit : string, optional
        Unit shown near the colorbar

    diff : Boolean, optional
        Switch to the color scale for difference plot
    '''

    assert isinstance(ax, GeoAxes), (
           "Input axis must be cartopy GeoAxes! "
           "Can be created by: \n"
           "plt.axes(projection=ccrs.PlateCarree()) \n or \n"
           "plt.subplots(n, m, subplot_kw={'projection': ccrs.PlateCarree()})"
           )
    assert ax.projection == ccrs.PlateCarree(), (
           'must use PlateCarree projection'
           )

    fig = ax.figure  # get parent figure

    if diff:
        vmax = np.max(np.abs(dr.values))
        vmin = -vmax
        cmap = cmap_diff
    else:
        vmax = np.max(dr.values)
        vmin = 0
        cmap = cmap_abs

    # imshow() is 6x faster than pcolormesh(), but with some limitations:
    # - only works with PlateCarree projection
    # - the left map boundary can't be smaller than -180,
    #   so the leftmost box (-182.5 for 4x5 grid) is slightly out of the map
    im = dr.plot.imshow(ax=ax, vmin=vmin, vmax=vmax, cmap=cmap,
                        transform=ccrs.PlateCarree(),
                        add_colorbar=False)

    # can also pass cbar_kwargs to dr.plot() to add colorbar,
    # but it is easier to tweak colorbar afterwards
    cb = fig.colorbar(im, ax=ax, shrink=0.6, orientation='horizontal', pad=0.1)
    cb.set_label(unit)

    # xarray automatically sets a title which might contain dimension info.
    # surpress it or use user-provided title
    ax.set_title(title)

    ax.coastlines()
    add_latlon_ticks(ax)  # add ticks and gridlines


def plot_zonal(dr, ax, title='', unit='', diff=False):
    '''Plot 2D DataArray as a zonal profile

    Parameters
    ----------
    dr : xarray.DataArray
        dimension should be [lev, lat]

    ax : matplotlib axes object
        Axis on which to plot this figure

    title : string, optional
        Title of the figure

    unit : string, optional
        Unit shown near the colorbar

    diff : Boolean, optional
        Switch to the color scale for difference plot
    '''

    # assume global field from 90S to 90N
    xtick_positions = np.array([-90, -60, -30, 0, 30, 60, 90])
    xticklabels = ['90$\degree$S',
                   '60$\degree$S',
                   '30$\degree$S',
                   '0$\degree$',
                   '30$\degree$N',
                   '60$\degree$N',
                   '90$\degree$N'
                   ]

    fig = ax.figure  # get parent figure

    # this code block largely duplicates plot_layer()
    # TODO: remove duplication
    if diff:
        vmax = np.max(np.abs(dr.values))
        vmin = -vmax
        cmap = cmap_diff
    else:
        vmax = np.max(dr.values)
        vmin = 0
        cmap = cmap_abs

    im = dr.plot.imshow(ax=ax, vmin=vmin, vmax=vmax, cmap=cmap,
                        add_colorbar=False)

    # the ratio of x-unit/y-unit in screen-space
    # 'auto' fills current figure with data without changing the figrue size
    ax.set_aspect('auto')

    ax.set_xticks(xtick_positions)
    ax.set_xticklabels(xticklabels)
    ax.set_xlabel('')
    ax.set_ylabel('Level')

    # can also pass cbar_kwargs to dr.plot() to add colorbar
    # but it is easier to tweak colorbar afterwards
    cb = fig.colorbar(im, ax=ax, shrink=0.6, orientation='horizontal', pad=0.1)
    cb.set_label(unit)

    ax.set_title(title)


def make_pdf(ds1, ds2, filename, on_map=True, diff=False,
             title1='DataSet 1', title2='DataSet 2', unit=''):
    '''Plot all variables in two 2D DataSets, and create a pdf.

    ds1 : xarray.DataSet
        shown on the left column

    ds2 : xarray.DataSet
        shown on the right column

    filename : string
        Name of the pdf file

    on_map : Boolean, optional
        If True (default), use plot_layer() to plot
        If False, use plot_zonal() to plot

    diff : Boolean, optional
        Switch to the color scale for difference plot

    title1, title2 : string, optional
        Title for each DataSet

    unit : string, optional
        Unit shown near the colorbar
    '''

    if on_map:
        plot_func = plot_layer
        subplot_kw = {'projection': ccrs.PlateCarree()}
    else:
        plot_func = plot_zonal
        subplot_kw = None

    # get a list of all variable names in ds1
    # assume ds2 also has those variables
    varname_list = list(ds1.data_vars.keys())

    n_var = len(varname_list)
    print('Benchmarking {} variables'.format(n_var))

    n_row = 3  # how many rows per page. TODO: should this be input argument?
    n_page = (n_var-1) // n_row + 1  # how many pages

    print('generating a {}-page pdf'.format(n_page))
    print('Page: ', end='')

    pdf = PdfPages(filename)

    for ipage in range(n_page):
        print(ipage, end=' ')
        fig, axes = plt.subplots(n_row, 2, figsize=[16, 16],
                                 subplot_kw=subplot_kw)

        # a list of 3 (n_row) variables names
        sub_varname_list = varname_list[n_row*ipage:n_row*(ipage+1)]

        for i, varname in enumerate(sub_varname_list):

            # Get min/max for both datasets to have same colorbar (ewl)
            #vmin = min([ds1[varname].data.min(), ds2[varname].data.min()])
            #vmax = max([ds1[varname].data.max(), ds2[varname].data.max()])

            for j, ds in enumerate([ds1, ds2]):
                if on_map:
                    plot_func(ds[varname], axes[i][j], unit=ds[varname].units, 
                              diff=diff)
                else:
                    # For now, assume zonal mean if plotting zonal (ewl)
                    plot_func(ds[varname].mean(axis=2), axes[i][j], 
                              unit=ds[varname].units, diff=diff)


            # TODO: tweak varname, e.g. Trim "TRC_O3" to "O3"
            axes[i][0].set_title(varname+'; '+title1)
            axes[i][1].set_title(varname+'; '+title2)

            # TODO: unit conversion according to data range of each variable,
            # e.g. mol/mol -> ppmv, ppbv, etc...

        pdf.savefig(fig)
        plt.close(fig)  # don't show in notebook!
    pdf.close()  # close it to save the pdf
    print('done!')

# Add docstrings later. Use this function for benchmarking or general comparisons.
def compare_single_level(refdata, refstr, devdata, devstr, varlist=None, ilev=0, itime=0,  weightsdir=None,
                         savepdf=False, pdfname='map.pdf', cmpres=None, match_cbar=True, normalize_by_area=False,
                         refarea=[], devarea=[], enforce_units=True, flip_ref=False, flip_dev=False ):

    # If no varlist is passed, plot all (surface only for 3D)
    if varlist == None:
        [varlist, commonvars2D, commonvars3D] = compare_varnames(refdata, devdata)
        print('Plotting all common variables (surface only if 3D)')
    n_var = len(varlist)

    ##############################################################################
    # Determine input grid resolutions and types
    ##############################################################################

    # ref
    refnlat = refdata.sizes['lat']
    refnlon = refdata.sizes['lon']
    if refnlat == 46 and refnlon == 72:
        refres = '4x5'
        refgridtype = 'll'
    elif refnlat == 91 and refnlon == 144:
        refres = '2x2.5'
        refgridtype = 'll'
    elif refnlat/6 == refnlon:
        refres = refnlon
        refgridtype = 'cs'
    else:
        print('ERROR: ref {}x{} grid not defined in gcpy!'.format(refnlat,refnlon))
        return
    
    # dev
    devnlat = devdata.sizes['lat']
    devnlon = devdata.sizes['lon']
    if devnlat == 46 and devnlon == 72:
        devres = '4x5'
        devgridtype = 'll'
    elif devnlat == 91 and devnlon == 144:
        devres = '2x2.5'
        devgridtype = 'll'
    elif devnlat/6 == devnlon:
        devres = devnlon
        devgridtype = 'cs'
    else:
        print('ERROR: dev {}x{} grid not defined in gcpy!'.format(refnlat,refnlon))
        return
    
    ##############################################################################
    # Determine comparison grid resolution and type (if not passed)
    ##############################################################################

    # If no cmpres is passed then choose highest resolution between ref and dev.
    # If both datasets are cubed sphere then default to 1x1.25 for comparison.
    if cmpres == None:
        if refres == devres and refgridtype == 'll':
            cmpres = refres
            cmpgridtype = 'll'
        elif refgridtype == 'll' and devgridtype == 'll':
            cmpres = min([refres, devres])
            cmpgridtype = 'll'
        elif refgridtype == 'cs' and devgridtype == 'cs':
            cmpres = max([refres, devres])
            cmpgridtype = 'cs'
        else:
            cmpres = '1x1.25'
            cmpgridtype = 'll'
    elif 'x' in cmpres:
        cmpgridtype = 'll'
    else:
        cmpgridtype = 'cs'
        
    # Determine what, if any, need regridding.
    regridref = refres != cmpres
    regriddev = devres != cmpres
    regridany = regridref or regriddev
    
    ##############################################################################
    # Make grids (ref, dev, and comparison)
    ##############################################################################

    # Ref
    if refgridtype == 'll':
        refgrid = make_grid_LL(refres)
    else:
        [refgrid, regrid_list] = make_grid_CS(refres)

    # Dev
    if devgridtype == 'll':
        devgrid = make_grid_LL(devres)
    else:
        [devgrid, devgrid_list] = make_grid_CS(devres)

    # Comparison    
    if cmpgridtype == 'll':
        cmpgrid = make_grid_LL(cmpres)
    else:
        [cmpgrid, cmpgrid_list] = make_grid_CS(cmpres)
        
    ##############################################################################
    # Make regridders, if applicable
    ##############################################################################

    if regridref:
        if refgridtype == 'll':
            refregridder = make_regridder_L2L(refres, cmpres, weightsdir=weightsdir, reuse_weights=True)
        else:
            refregridder_list = make_regridder_C2L(refres, cmpres, weightsdir=weightsdir, reuse_weights=True)
    if regriddev:
        if devgridtype == 'll':
            devregridder = make_regridder_L2L(devres, cmpres, weightsdir=weightsdir, reuse_weights=True)
        else:
            devregridder_list = make_regridder_C2L(devres, cmpres, weightsdir=weightsdir, reuse_weights=True)

    ##############################################################################
    # Get lat/lon extents, if applicable
    ##############################################################################
    
    if refgridtype == 'll':
        [refminlon, refmaxlon] = [min(refgrid['lon_b']), max(refgrid['lon_b'])]
        [refminlat, refmaxlat] = [min(refgrid['lat_b']), max(refgrid['lat_b'])]
    if devgridtype == 'll':
        [devminlon, devmaxlon] = [min(devgrid['lon_b']), max(devgrid['lon_b'])]
        [devminlat, devmaxlat] = [min(devgrid['lat_b']), max(devgrid['lat_b'])]
    if cmpgridtype == 'll':
        [cmpminlon, cmpmaxlon] = [min(cmpgrid['lon_b']), max(cmpgrid['lon_b'])]
        [cmpminlat, cmpmaxlat] = [min(cmpgrid['lat_b']), max(cmpgrid['lat_b'])]

    ##############################################################################
    # Create pdf, if savepdf is passed as True
    ##############################################################################
    
    if savepdf:
        print('\nCreating {} for {} variables'.format(pdfname,n_var))
        pdf = PdfPages(pdfname)

    ##############################################################################
    # Loop over variables
    ##############################################################################
    
    print_units_warning = True
    for ivar in range(n_var):
        if savepdf: print('{} '.format(ivar), end='')
        varname = varlist[ivar]
        
        # Do some checks: dimensions and units
        varndim_ref = refdata[varname].ndim
        varndim_dev = devdata[varname].ndim      
        units_ref = refdata[varname].units.strip()
        units_dev = devdata[varname].units.strip()
        if units_ref != units_dev:
            if print_units_warning:
                print('WARNING: ref and dev concentration units do not match!')
                print('Ref units: {}'.format(units_ref))
                print('Dev units: {}'.format(units_dev))
            if enforce_units:
            # if enforcing units, stop the program if units do not match
               assert units_ref == units_dev, 'Units do not match for {}!'.format(varname)
            else:
               # if not enforcing units, just keep going after only printing warning once 
               print_units_warning = False
               
        ##############################################################################
        # Slice the data, allowing for possibility of no time dimension (bpch)
        ##############################################################################

        # Ref
        vdims = refdata[varname].dims
        if 'time' in vdims and 'lev' in vdims: 
            if flip_ref:
                ds_ref = refdata[varname].isel(time=itime,lev=71-ilev)
            else:
                ds_ref = refdata[varname].isel(time=itime,lev=ilev)
        elif 'lev' in vdims:
            if flip_ref:
                ds_ref = refdata[varname].isel(lev=71-ilev)
            else:
                ds_ref = refdata[varname].isel(lev=ilev)
        elif 'time' in vdims: 
            ds_ref = refdata[varname].isel(time=itime)
        else:
            ds_ref = refdata[varname]

        # Dev
        vdims = devdata[varname].dims
        if 'time' in vdims and 'lev' in vdims: 
            if flip_dev:
                ds_dev = devdata[varname].isel(time=itime,lev=71-ilev)
            else:
                ds_dev = devdata[varname].isel(time=itime,lev=ilev)
        elif 'lev' in vdims:
            if flip_dev:
                ds_dev = devdata[varname].isel(lev=71-ilev)
            else:
                ds_dev = devdata[varname].isel(lev=ilev)
        elif 'time' in vdims: 
            ds_dev = devdata[varname].isel(time=itime)
        else:
            ds_dev = devdata[varname]
            
        ##############################################################################
        # Area normalization, if any
        ##############################################################################    

        # if normalizing by area, adjust units to be per m2, and adjust title string
        units = units_ref
        subtitle_extra = ''
        varndim = varndim_ref # gchp only?

        # if regridding then normalization by area may be necessary. Either pass normalize_by_area=True to normalize all,
        # or include units that should always be normalized by area below. If comparing HEMCO diagnostics then the
        # areas for ref and dev must be passed; otherwise they are included in the HISTORY diagnostics file and do
        # not need to be passed.
        exclude_list = ['WetLossConvFrac','Prod_','Loss_']
        if regridany and ( ( units == 'kg' or units == 'kgC' ) or normalize_by_area ):
            if not any(s in varname for s in exclude_list):
                if len(refarea) == 0 and len(devarea) == 0:
                    ds_ref.values = ds_ref.values / refdata['AREAM2'].values
                    ds_dev.values = ds_dev.values / devdata['AREAM2'].values
                else:
                    ds_ref.values = ds_ref.values / refarea
                    ds_dev.values = ds_dev.values / devarea               
                units = '{}/m2'.format(units)
                units_ref = units
                units_dev = units
                subtitle_extra = ', Normalized by Area'

        ##############################################################################    
        # Get comparison data sets, regridding the input slices if needed
        ##############################################################################

        # Reshape ref/dev cubed sphere data, if any
        if refgridtype == 'cs':
            ds_ref_reshaped = ds_ref.data.reshape(6,refres,refres)
        if devgridtype == 'cs':
            ds_dev_reshaped = ds_dev.data.reshape(6,devres,devres)

        # Ref
        if regridref:
            if refgridtype == 'll':
                # regrid ll to ll
                ds_ref_cmp = refregridder(ds_ref)
            else:
                # regrid cs to ll
                ds_ref_cmp = np.zeros([cmpgrid['lat'].size, cmpgrid['lon'].size])
                for i in range(6):
                    regridder = refregridder_list[i]
                    ds_ref_cmp += regridder(ds_ref_reshaped[i])
        else:
            ds_ref_cmp = ds_ref

        # Dev
        if regriddev:
            if devgridtype == 'll':
                # regrid ll to ll
                ds_dev_cmp = devregridder(ds_dev)
            else:
                # regrid cs to ll
                ds_dev_cmp = np.zeros([cmpgrid['lat'].size, cmpgrid['lon'].size])
                for i in range(6):
                    regridder = devregridder_list[i]
                    ds_dev_cmp += regridder(ds_dev_reshaped[i])
        else:
            ds_dev_cmp = ds_dev

        # Reshape comparison cubed sphere data, if any
        if cmpgridtype == 'cs':
            ds_ref_cmp_reshaped = ds_ref_cmp.data.reshape(6,cmpres,cmpres)
            ds_dev_cmp_reshaped = ds_dev_cmp.data.reshape(6,cmpres,cmpres)

        ##############################################################################    
        # Get min and max values for use in the colorbars
        ##############################################################################

        # Ref
        if refgridtype == 'cs':
            vmin_ref = ds_ref_reshaped.min()
            vmax_ref = ds_ref_reshaped.max()
        else:
            vmin_ref = ds_ref.min()
            vmax_ref = ds_ref.max()

        # Dev
        if devgridtype == 'cs':
            vmin_dev = ds_dev_reshaped.min()
            vmax_dev = ds_dev_reshaped.max()
        else:
            vmin_dev = ds_dev.min()
            vmax_dev = ds_dev.max()

        # Comparison
        if cmpgridtype == 'cs':
            vmin_ref_cmp = ds_ref_cmp_reshaped.min()
            vmax_ref_cmp = ds_ref_cmp_reshaped.max()
            vmin_dev_cmp = ds_dev_cmp_reshaped.min()
            vmax_dev_cmp = ds_dev_cmp_reshaped.max()
            vmin_cmp = np.min([vmin_ref_cmp, vmin_dev_cmp])
            vmax_cmp = np.max([vmax_ref_cmp, vmax_dev_cmp]) 
        else:
            vmin_cmp = np.min([ds_ref_cmp.min(), ds_dev_cmp.min()])
            vmax_cmp = np.max([ds_ref_cmp.max(), ds_dev_cmp.max()])

        # Take min/max across all
        vmin_abs = np.min([vmin_ref, vmin_dev, vmin_cmp])
        vmax_abs = np.max([vmax_ref, vmax_dev, vmax_cmp])
        if match_cbar: [vmin, vmax] = [vmin_abs, vmax_abs]

        ##############################################################################    
        # Create 3x2 figure
        ##############################################################################
        
        figs, ((ax0, ax1), (ax2, ax3), (ax4, ax5)) = plt.subplots(3, 2, figsize=[12,14], 
                                                      subplot_kw={'projection': crs.PlateCarree()})
        # Give the figure a title
        offset = 0.96
        fontsize=25
        
        if 'lev' in refdata[varname].dims and 'lev' in devdata[varname].dims:
            if ilev == 0: levstr = 'Surface'
            elif ilev == 22: levstr = '500 hPa'
            else: levstr = 'Level ' +  str(ilev-1)
            figs.suptitle('{}, {}'.format(varname,levstr), fontsize=fontsize, y=offset)
        elif 'lat' in refdata[varname].dims and 'lat' in devdata[varname] and 'lon' in refdata[varname].dims and 'lon' in devdata[varname]: 
            figs.suptitle('{}'.format(varname), fontsize=fontsize, y=offset)
        else:
            print('Incorrect dimensions for {}!'.format(varname))   

        ##############################################################################    
        # Subplot (0,0): Ref, plotted on ref input grid
        ##############################################################################
        
        ax0.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_ref, vmax_ref]
        if refgridtype == 'll':
            plot0 = ax0.imshow(ds_ref, extent=(refminlon, refmaxlon, refminlat, refmaxlat), 
                               cmap=WhGrYlRd, vmin=vmin, vmax=vmax)
        else:
            masked_refdata = np.ma.masked_where(np.abs(refgrid['lon'] - 180) < 2, ds_ref_reshaped)
            for i in range(6):
                plot0 = ax0.pcolormesh(refgrid['lon_b'][i,:,:], refgrid['lat_b'][i,:,:], masked_refdata[i,:,:], 
                                       cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax0.set_title('{} (Ref){}\n{}'.format(refstr,subtitle_extra,refres)) 
        cb = plt.colorbar(plot0, ax=ax0, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units_ref)

        ##############################################################################    
        # Subplot (0,1): Dev, plotted on dev input grid
        ##############################################################################
                
        ax1.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_dev, vmax_dev]
        if devgridtype == 'll':
            plot1 = ax1.imshow(ds_dev, extent=(devminlon, devmaxlon, devminlat, devmaxlat), 
                               cmap=WhGrYlRd, vmin=vmin, vmax=vmax)
        else:
            masked_devdata = np.ma.masked_where(np.abs(devgrid['lon'] - 180) < 2, ds_dev_reshaped)
            for i in range(6):
                plot1 = ax1.pcolormesh(devgrid['lon_b'][i,:,:], devgrid['lat_b'][i,:,:], 
                                       masked_devdata[i,:,:], cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax1.set_title('{} (Dev){}\n{}'.format(devstr,subtitle_extra,devres)) 
        cb = plt.colorbar(plot1, ax=ax1, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units_dev)

        ##############################################################################    
        # Calculate difference, get dynamic range, configure colorbar, use gray for NaNs
        ##############################################################################
        
        if cmpgridtype == 'll':
            absdiff = np.array(ds_dev_cmp) - np.array(ds_ref_cmp)
        else:
            absdiff = ds_dev_cmp_reshaped - ds_ref_cmp_reshaped
            masked_absdiff = np.ma.masked_where(np.abs(cmpgrid['lon'] - 180) < 2, absdiff)
        diffabsmax = max([np.abs(np.nanmin(absdiff)), np.abs(np.nanmax(absdiff))])        
        cmap = mpl.cm.RdBu_r
        cmap.set_bad(color='gray')
            
        ##############################################################################    
        # Subplot (1,0): Difference, dynamic range
        ##############################################################################

        [vmin, vmax] = [-diffabsmax, diffabsmax]
        ax2.coastlines()
        if cmpgridtype == 'll':
            plot2 = ax2.imshow(absdiff, extent=(cmpminlon, cmpmaxlon, cmpminlat, cmpmaxlat), 
                               cmap=cmap,vmin=vmin, vmax=vmax)
        else:
            for i in range(6):
                plot2 = ax2.pcolormesh(cmpgrid['lon_b'][i,:,:], cmpgrid['lat_b'][i,:,:], 
                                       masked_absdiff[i,:,:], cmap='RdBu_r',vmin=vmin, vmax=vmax)
        if regridany:
            ax2.set_title('Difference ({})\nDev - Ref, Dynamic Range'.format(cmpres))
        else:
            ax2.set_title('Difference\nDev - Ref, Dynamic Range')
        cb = plt.colorbar(plot2, ax=ax2, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        if np.all(absdiff==0): 
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0']) 

        ##############################################################################    
        # Subplot (1,1): Difference, restricted range
        ##############################################################################

        # placeholder: use 5 and 95 percentiles as bounds
        [pct5, pct95] = [np.percentile(absdiff,5), np.percentile(absdiff, 95)] 

        abspctmax = np.max([np.abs(pct5),np.abs(pct95)])
        [vmin,vmax] = [-abspctmax, abspctmax]
        ax3.coastlines()
        if cmpgridtype == 'll':
            plot3 = ax3.imshow(absdiff, extent=(cmpminlon, cmpmaxlon, cmpminlat, cmpmaxlat), 
                               cmap=cmap,vmin=vmin, vmax=vmax)
        else:
            for i in range(6):
                plot3 = ax3.pcolormesh(cmpgrid['lon_b'][i,:,:], cmpgrid['lat_b'][i,:,:], 
                                       masked_absdiff[i,:,:], cmap='RdBu_r',vmin=vmin, vmax=vmax)
        if regridany:
            ax3.set_title('Difference ({})\nDev - Ref, Restricted Range [5%,95%]'.format(cmpres))
        else:
            ax3.set_title('Difference\nDev - Ref, Restricted Range [5%,95%]')            
        cb = plt.colorbar(plot3, ax=ax3, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        if np.all(absdiff==0): 
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])

        ##############################################################################    
        # Calculate fractional difference, get dynamic range, set 0/0 to Nan
        ##############################################################################
        
        if cmpgridtype == 'll':
            fracdiff = (np.array(ds_dev_cmp) - np.array(ds_ref_cmp)) / np.array(ds_ref_cmp)
            fracdiff[(ds_dev_cmp == 0) & (ds_ref_cmp == 0)] = np.nan
        else:
            fracdiff = (ds_dev_cmp_reshaped - ds_ref_cmp_reshaped) / ds_ref_cmp_reshaped
            fracdiff[(ds_dev_cmp_reshaped == 0) & (ds_ref_cmp_reshaped == 0)] = np.nan
            masked_fracdiff = np.ma.masked_where(np.abs(cmpgrid['lon'] - 180) < 2, fracdiff)
        fracdiffabsmax = max([np.abs(np.nanmin(fracdiff)), np.abs(np.nanmax(fracdiff))])

        ##############################################################################    
        # Subplot (2,0): Fractional Difference, full dynamic range
        ##############################################################################
        
        [vmin, vmax] = [-fracdiffabsmax, fracdiffabsmax]
        ax4.coastlines()
        if cmpgridtype == 'll':
            plot4 = ax4.imshow(fracdiff, extent=(cmpminlon, cmpmaxlon, cmpminlat, cmpmaxlat),
                               vmin=vmin, vmax=vmax, cmap=cmap)
        else:
            for i in range(6):
                plot4 = ax4.pcolormesh(cmpgrid['lon_b'][i,:,:], cmpgrid['lat_b'][i,:,:], 
                                   masked_fracdiff[i,:,:], cmap='RdBu_r',vmin=vmin, vmax=vmax)
        if regridany:
            ax4.set_title('Fractional Difference ({})\n(Dev-Ref)/Ref, Dynamic Range'.format(cmpres)) 
        else:
            ax4.set_title('Fractional Difference\n(Dev-Ref)/Ref, Dynamic Range') 
        cb = plt.colorbar(plot4, ax=ax4, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
            if np.all(absdiff==0): 
                cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])
        cb.set_label('unitless')  

        ##############################################################################    
        # Subplot (2,1): Fractional Difference, restricted
        ##############################################################################
        
        [vmin, vmax] = [-2, 2]
        #[vmin, vmax] = [-0.5, 2] # doesn't work with this colorbar. Need to customize one. Already in gamap?
                                  # Switch to this if change to ratios (dev/ref)
        ax5.coastlines()
        if cmpgridtype == 'll':
            plot5 = ax5.imshow(fracdiff, extent=(cmpminlon, cmpmaxlon, cmpminlat, cmpmaxlat),
                               cmap=cmap,vmin=vmin, vmax=vmax)
        else:
            for i in range(6):
                plot5 = ax5.pcolormesh(cmpgrid['lon_b'][i,:,:], cmpgrid['lat_b'][i,:,:], 
                                   masked_fracdiff[i,:,:], cmap='RdBu_r',vmin=vmin, vmax=vmax)
        if regridany:
            ax5.set_title('Fractional Difference ({})\n(Dev-Ref)/Ref, Fixed Range'.format(cmpres))
        else:
            ax5.set_title('Fractional Difference\n(Dev-Ref)/Ref, Fixed Range') 
        cb = plt.colorbar(plot5, ax=ax5, orientation='horizontal', pad=0.10)
        if np.all(absdiff==0): 
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])
        cb.set_label('unitless') 
            
        if savepdf:    
            pdf.savefig(figs)
            plt.close(figs)

    ##############################################################################    
    # Finish
    ##############################################################################

    if savepdf: pdf.close()

def compare_gchp_single_level(refdata, refstr, devdata, devstr, varlist=None, weightsdir='.', ilev=0, 
                         itime=0, savepdf=False, pdfname='gchp_vs_gchp_map.pdf', match_cbar=True, 
                         full_ratio_range=False, normalize_by_area=False, area_ref=None, 
                         area_dev=None, check_units=True, flip_vert=False):
    
    # If no varlist is passed, plot all (surface only for 3D)
    if varlist == None:
        [varlist, commonvars2D, commonvars3D] = compare_varnames(refdata, devdata)
        print('Plotting all common variables (surface only if 3D)')
    n_var = len(varlist)

    # Get cubed sphere grids and regridder 
    # for now, do not regrid for gchp vs gchp. Assume same grid.
    csres_ref = refdata['lon'].size
    [csgrid_ref, csgrid_list_ref] = make_grid_CS(csres_ref)
    csres_dev = devdata['lon'].size
    [csgrid_dev, csgrid_list_dev] = make_grid_CS(csres_dev)

    # Create pdf (if saving)
    if savepdf:
        print('\nCreating {} for {} variables'.format(pdfname,n_var))
        pdf = PdfPages(pdfname)

    # Loop over variables
    for ivar in range(n_var):
        if savepdf: print('{} '.format(ivar), end='')
        varname = varlist[ivar]
        
        # Do some checks: dimensions and units
        varndim_ref = refdata[varname].ndim
        varndim_dev = devdata[varname].ndim
        if check_units: 
            assert varndim_ref == varndim_dev, 'Dimensions do not agree for {}!'.format(varname)
        units_ref = refdata[varname].units
        units_dev = devdata[varname].units
        if check_units: 
            assert units_ref == units_dev, 'Units do not match for {}!'.format(varname)
            
        # if normalizing by area, adjust units to be per m2, and adjust title string
        units = units_ref
        varndim = varndim_ref
        subtitle_extra = ''
                    
        # Slice the data
        vdims = refdata[varname].dims
        if 'time' in vdims and 'lev' in vdims: 
            if flip_vert: 
                ds_ref = refdata[varname].isel(time=itime,lev=71-ilev)
                ds_dev = devdata[varname].isel(time=itime,lev=71-ilev)
            else: 
                ds_ref = refdata[varname].isel(time=itime,lev=ilev)
                ds_dev = devdata[varname].isel(time=itime,lev=ilev)
        elif 'lev' in vdims: 
            if flip_vert: 
                ds_ref = refdata[varname].isel(lev=71-ilev)
                ds_dev = devdata[varname].isel(lev=71-ilev)
            else: 
                ds_ref = refdata[varname].isel(lev=ilev)
                ds_dev = devdata[varname].isel(lev=ilev)
        elif 'time' in vdims:
            ds_ref = refdata[varname].isel(time=itime)
            ds_dev = devdata[varname].isel(time=itime)
        elif 'lat' in vdims and 'lon' in vdims:
            ds_ref = refdata[varname]
            ds_dev = devdata[varname]
        else:
            print('ERROR: cannot handle variables without lat and lon dimenions.')
            print(varname)
            
        # if normalizing by area, transform on the native grid and adjust units and subtitle string
        exclude_list = ['WetLossConvFrac','Prod_','Loss_']
        if normalize_by_area and not any(s in varname for s in exclude_list):
            ds_ref.values = ds_ref.values / area_ref
            ds_dev.values = ds_dev.values / area_dev
            units = '{} m-2'.format(units)
            subtitle_extra = ', Normalized by Area'
            
        # Get min and max for use in colorbars
        csdata_ref = ds_ref.data.reshape(6,csres_ref,csres_ref)
        csdata_dev = ds_dev.data.reshape(6,csres_dev,csres_dev)
        vmin_ref = csdata_ref.min()
        vmin_dev = csdata_dev.min()
        vmin_cmp = np.min([vmin_ref, vmin_dev])
        vmax_ref = csdata_ref.max()
        vmax_dev = csdata_dev.max()
        vmax_cmp = np.max([vmax_ref, vmax_dev])
        if match_cbar: [vmin, vmax] = [vmin_cmp, vmax_cmp]
        
        # Create 2x2 figure
        figs, ((ax0, ax1), (ax2, ax3)) = plt.subplots(2, 2, figsize=[12,9], 
                                                      subplot_kw={'projection': crs.PlateCarree()})
        # Give the figure a title
        offset = 0.96
        fontsize=25
        if 'lev' in vdims: 
            if ilev == 0: levstr = 'Surface'
            elif ilev == 22: levstr = '500 hPa'
            else: levstr = 'Level ' +  str(ilev-1)
            figs.suptitle('{}, {}'.format(varname,levstr), fontsize=fontsize, y=offset)
        else: 
            figs.suptitle('{}'.format(varname), fontsize=fontsize, y=offset)
            
        # Subplot (0,0): Ref
        ax0.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_ref, vmax_ref]        
        masked_csdata = np.ma.masked_where(np.abs(csgrid_ref['lon'] - 180) < 2, csdata_ref)
        for i in range(6):
            plot0 = ax0.pcolormesh(csgrid_ref['lon_b'][i,:,:], csgrid_ref['lat_b'][i,:,:], masked_csdata[i,:,:], 
                                   cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax0.set_title('{} (Ref){}\nC{}'.format(refstr,subtitle_extra,str(csres_ref)))
        cb = plt.colorbar(plot0, ax=ax0, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)     
        
        # Subplot (0,1): Dev
        ax1.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_dev, vmax_dev]        
        masked_csdata = np.ma.masked_where(np.abs(csgrid_dev['lon'] - 180) < 2, csdata_dev)
        for i in range(6):
            plot1 = ax1.pcolormesh(csgrid_dev['lon_b'][i,:,:], csgrid_dev['lat_b'][i,:,:], 
                                   masked_csdata[i,:,:], cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax1.set_title('{} (Dev){}\nC{}'.format(devstr,subtitle_extra,str(csres_dev)))
        cb = plt.colorbar(plot1, ax=ax1, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)  
            
        # Subplot (1,0): Difference
        gc_absdiff = csdata_dev - csdata_ref
        diffabsmax = max([np.abs(gc_absdiff.min()), np.abs(gc_absdiff.max())])
        [vmin, vmax] = [-diffabsmax, diffabsmax]
        ax2.coastlines()
        # assume the same grid for now in gchp vs gchp
        masked_csdata = np.ma.masked_where(np.abs(csgrid_dev['lon'] - 180) < 2, gc_absdiff)
        for i in range(6):
            plot2 = ax2.pcolormesh(csgrid_dev['lon_b'][i,:,:], csgrid_dev['lat_b'][i,:,:], 
                                   masked_csdata[i,:,:], cmap='RdBu_r',vmin=vmin, vmax=vmax)
        ax2.set_title('Difference\n(Dev - Ref)')   
        cb = plt.colorbar(plot2, ax=ax2, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)  
    
        # Subplot (1,1): Fractional Difference (restrict to +/-2)
        gc_fracdiff = (csdata_dev - csdata_ref) / csdata_ref
        if full_ratio_range: [vmin, vmax] = [None, None]
        else: [vmin, vmax] = [-2, 2]
        ax3.coastlines()
        # assume the same grid for now in gchp vs gchp
        masked_csdata = np.ma.masked_where(np.abs(csgrid_dev['lon'] - 180) < 2, gc_fracdiff)
        for i in range(6):
            plot3 = ax3.pcolormesh(csgrid_dev['lon_b'][i,:,:], csgrid_dev['lat_b'][i,:,:], 
                                   masked_csdata[i,:,:], cmap='RdBu_r',vmin=vmin, vmax=vmax)
        ax3.set_title('Fractional Difference\n(Dev - Ref)/Ref')   
        cb = plt.colorbar(plot3, ax=ax3, orientation='horizontal', pad=0.10)
        cb.set_clim(vmin=vmin, vmax=vmax)
        cb.set_label('unitless')     
            
        if savepdf:    
            pdf.savefig(figs)
            plt.close(figs)
            
    if savepdf: pdf.close()

def compare_gchp_vs_gcc_single_level(dgcc, dgchp, varlist=None, weightsdir='.', ilev=0, itime=0,
                                     llres_raw='4x5', llres_cmp='1x1.25', savepdf=False,
                                     pdfname='gchp_vs_gcc_map.pdf', match_cbar=True, full_ratio_range=False,
                                     normalize_by_area=False, area1=None, area2=None, check_units=True, flip_vert=False):
    
    # If no varlist is passed, plot all (surface only for 3D)
    if varlist == None:
        [varlist, commonvars2D, commonvars3D] = compare_varnames(dgcc, dgchp)
        print('Plotting all common variables (surface only if 3D)')
    n_var = len(varlist)
    
    # Get lat-lon grids and regridder. Assume regridding weights have already been generated
    llgrid_raw = make_grid_LL(llres_raw)
    llgrid_cmp = make_grid_LL(llres_cmp)
    ll_regridder = make_regridder_L2L(llres_raw, llres_cmp, weightsdir=weightsdir, reuse_weights=True)

    # Get cubed sphere grid and regridder
    csres = dgchp['lon'].size
    [csgrid, csgrid_list] = make_grid_CS(csres)
    cs_regridder_list = make_regridder_C2L(csres, llres_cmp, weightsdir=weightsdir, reuse_weights=True)

    # Get lat/lon extents
    [minlon_raw, maxlon_raw] = [min(llgrid_raw['lon_b']), max(llgrid_raw['lon_b'])]
    [minlat_raw, maxlat_raw] = [min(llgrid_raw['lat_b']), max(llgrid_raw['lat_b'])]
    [minlon_cmp, maxlon_cmp] = [min(llgrid_cmp['lon_b']), max(llgrid_cmp['lon_b'])]
    [minlat_cmp, maxlat_cmp] = [min(llgrid_cmp['lat_b']), max(llgrid_cmp['lat_b'])]

    # Create pdf (if saving)
    if savepdf:
        print('\nCreating {} for {} variables'.format(pdfname,n_var))
        pdf = PdfPages(pdfname)

    # Loop over variables
    for ivar in range(n_var):
        if savepdf: print('{} '.format(ivar), end='')
        varname = varlist[ivar]
        
        # Do some checks: dimensions and units
        varndim = dgchp[varname].ndim
        varndim2 = dgcc[varname].ndim
        if check_units: assert varndim == varndim2, 'GCHP and GCC dimensions do not agree for {}!'.format(varname)
        units_raw = dgchp[varname].units
        units2 = dgcc[varname].units
        if check_units: assert units_raw == units2, 'GCHP and GCC units do not match for {}!'.format(varname)
            
        # if normalizing by area, adjust units to be per m2, and adjust title string
        units = units_raw
        subtitle_extra = ''
                 
        # Slice the data
        if varndim == 4: 
            if 'ilev' in dgcc[varname].dims:
                ds1 = dgcc[varname].isel(time=itime,ilev=ilev)
            else:
                ds1 = dgcc[varname].isel(time=itime,lev=ilev)
            if flip_vert: ds2 = dgchp[varname].isel(time=itime,lev=71-ilev)
            else: ds2 = dgchp[varname].isel(time=itime,lev=ilev)
        elif varndim == 3: 
            ds1 = dgcc[varname].isel(time=itime)
            ds2 = dgchp[varname].isel(time=itime)
            
        # if normalizing by area, transform on the native grid and adjust units and subtitle string
        exclude_list = ['WetLossConvFrac','Prod_','Loss_']
        if normalize_by_area and not any(s in varname for s in exclude_list):
            ds1.values = ds1.values / area1
            ds2.values = ds2.values / area2
            units = '{} m-2'.format(units_raw)
            subtitle_extra = ', Normalized by Area'
            
        # Regrid the slices
        csdata = ds2.data.reshape(6,csres,csres)
        gchp_ll = np.zeros([llgrid_cmp['lat'].size, llgrid_cmp['lon'].size])
        for i in range(6):
            regridder = cs_regridder_list[i]
            gchp_ll += regridder(csdata[i])
        gcc_ll = ll_regridder(ds1)
        
        # Get min and max for colorbar limits
        vmin_gchp = np.min([csdata.min(), gchp_ll.min()])
        vmin_gcc = np.min([ds1.values.min(), gcc_ll.values.min()])
        vmin_cmn = np.min([vmin_gchp, vmin_gcc])
        vmax_gchp = np.max([csdata.max(), gchp_ll.max()])
        vmax_gcc = np.max([ds1.values.max(), gcc_ll.values.max()])
        vmax_cmn = np.max([vmax_gchp, vmax_gcc])
        if match_cbar: [vmin, vmax] = [vmin_cmn, vmax_cmn]
        
        # Create 3x2 figure
        figs, ((ax0, ax1), (ax2, ax3), (ax4, ax5)) = plt.subplots(3, 2, 
                                                                  figsize=[12,14], 
                                                                  subplot_kw={'projection': crs.PlateCarree()})
        # Give the figure a title
        offset = 0.96
        fontsize=25
        if varndim == 4:
            if ilev == 0: levstr = 'Surface'
            elif ilev == 22: levstr = '500 hPa'
            else: levstr = 'Level ' +  str(ilev-1)
            figs.suptitle('{}, {}'.format(varname,levstr), fontsize=fontsize, y=offset)
        elif varndim == 3: 
            figs.suptitle('{}'.format(varname), fontsize=fontsize, y=offset)
        else:
            print('varndim is 2 for {}! Must be 3 or 4.'.format(varname))
            
        # Set bounds of auto-tick range
        
            
        # Subplot (0,0): GCHP raw
        ax0.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_gchp, vmax_gchp]        
        masked_csdata = np.ma.masked_where(np.abs(csgrid['lon'] - 180) < 2, csdata) # based on cubedsphere plotCS_quick_raw
        for i in range(6):
            plot0 = ax0.pcolormesh(csgrid['lon_b'][i,:,:], csgrid['lat_b'][i,:,:], masked_csdata[i,:,:], 
                                   cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax0.set_title('GCHP Raw{}\nC{}'.format(subtitle_extra,str(csres)))
        cb = plt.colorbar(plot0, ax=ax0, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)            
        
        # Subplot (0,1): GCHP regridded
        ax1.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_gchp, vmax_gchp]
        plot1 = ax1.imshow(gchp_ll, extent=(minlon_cmp, maxlon_cmp, minlat_cmp, maxlat_cmp), 
                           cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax1.set_title('GCHP Regridded\n{}'.format(llres_cmp))
        cb = plt.colorbar(plot1, ax=ax1, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot (1,0): GCC raw
        ax2.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_gcc, vmax_gcc]
        plot2 = ax2.imshow(ds1, extent=(minlon_raw, maxlon_raw, minlat_raw, maxlat_raw), 
                           cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax2.set_title('GCC Raw{}\n{}'.format(subtitle_extra,llres_raw)) 
        cb = plt.colorbar(plot2, ax=ax2, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot (1,1): GCC regridded
        ax3.coastlines()
        if not match_cbar: [vmin, vmax] = [vmin_gcc, vmax_gcc]
        plot3 = ax3.imshow(gcc_ll, extent=(minlon_cmp, maxlon_cmp, minlat_cmp, maxlat_cmp), 
                           cmap=WhGrYlRd,vmin=vmin, vmax=vmax)
        ax3.set_title('GCC Regridded\n{}'.format(llres_cmp))
        cb = plt.colorbar(plot3, ax=ax3, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
            
        # Subplot (2,0): Difference
        gc_absdiff = gchp_ll - gcc_ll
        diffabsmax = max([np.abs(gc_absdiff.min()), np.abs(gc_absdiff.max())])
        [vmin, vmax] = [-diffabsmax, diffabsmax]
        ax4.coastlines()
        gc_absdiff.plot.imshow
        plot4 = ax4.imshow(gc_absdiff, cmap='RdBu_r', extent=(minlon_cmp, maxlon_cmp, minlat_cmp, maxlat_cmp), 
                           vmin=vmin, vmax=vmax)
        ax4.set_title('Difference\n(GCHP - GCC)')
        cb = plt.colorbar(plot4, ax=ax4, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot (2,1): Fractional Difference (restrict to +/-2)
        gc_fracdiff = (gchp_ll - gcc_ll) / gcc_ll
        if full_ratio_range: [vmin, vmax] = [None, None]
        else: [vmin, vmax] = [-2, 2]
        ax5.coastlines()
        plot5 = ax5.imshow(gc_fracdiff, vmin=vmin, vmax=vmax, cmap='RdBu_r', 
                           extent=(minlon_cmp, maxlon_cmp, minlat_cmp, maxlat_cmp))
        ax5.set_title('Fractional Difference\n(GCHP-GCC)/GCC')
        cb = plt.colorbar(plot5, ax=ax5, orientation='horizontal', pad=0.10)
        cb.set_clim(vmin=vmin, vmax=vmax)
        cb.set_label('unitless')      
            
        if savepdf:    
            pdf.savefig(figs)
            plt.close(figs)
            
    if savepdf: pdf.close()


# Add docstrings later. Use this function for benchmarking or general comparisons.
def compare_zonal_mean(refdata, refstr, devdata, devstr, varlist=None, itime=0, weightsdir=None,
                       savepdf=False, pdfname='zonalmean.pdf', cmpres=None, match_cbar=True,
                       normalize_by_area=False, enforce_units=True ):

    # If no refres is passed, determine automatically from sizes of lat and lon
    refnlat = refdata.sizes['lat']
    refnlon = refdata.sizes['lon']
    devnlat = devdata.sizes['lat']
    devnlon = devdata.sizes['lon']
    
    # ref grid resolution and type
    if refnlat == 46 and refnlon == 72:
        refres = '4x5'
        refgridtype = 'll'
    elif refnlat == 91 and refnlon == 144:
        refres = '2x2.5'
        refgridtype = 'll'
    else:
        print('ERROR: ref {}x{} grid not defined in gcpy!'.format(refnlat,refnlon))
        return

    # dev grid resolution and type
    if devnlat == 46 and devnlon == 72:
        devres = '4x5'
        devgridtype = 'll'
    elif devnlat == 91 and devnlon == 144:
        devres = '2x2.5'
        devgridtype = 'll'
    else:
        print('ERROR: dev {}x{} grid not defined in gcpy!'.format(refnlat,refnlon))
        return
    
    # If no varlist is passed, plot all 3D variables in the dataset
    if varlist == None:
        [commonvars, commonvars2D, varlist] = compare_varnames(refdata, devdata)
        print('Plotting all 3D variables')
    n_var = len(varlist)

    # If no cmpres is passed then choose highest resolution between ref and dev.
    if cmpres == None:
        if refres == devres:
            cmpres = refres
        else:
            cmpres = min([refres, devres])

    # Determine what, if any, need regridding.
    regridref = refres != cmpres
    regriddev = devres != cmpres
    regridany = regridref or regriddev

    # Get lat-lon grids (ref, dev, and comparison)
    if refgridtype == 'll': refgrid = make_grid_LL(refres)
    if devgridtype == 'll': devgrid = make_grid_LL(devres)
    cmpgrid = make_grid_LL(cmpres)
    if regridref and refgridtype == 'll':
        refregridder = make_regridder_L2L(refres, cmpres, weightsdir=weightsdir, reuse_weights=True)
    if regriddev and devgridtype == 'll':
        devregridder = make_regridder_L2L(devres, cmpres, weightsdir=weightsdir, reuse_weights=True)
    
    # Get lat/lon extents
    [refminlon, refmaxlon] = [min(refgrid['lon_b']), max(refgrid['lon_b'])]
    [refminlat, refmaxlat] = [min(refgrid['lat_b']), max(refgrid['lat_b'])]
    [devminlon, devmaxlon] = [min(devgrid['lon_b']), max(devgrid['lon_b'])]
    [devminlat, devmaxlat] = [min(devgrid['lat_b']), max(devgrid['lat_b'])]
    [cmpminlon, cmpmaxlon] = [min(cmpgrid['lon_b']), max(cmpgrid['lon_b'])]
    [cmpminlat, cmpmaxlat] = [min(cmpgrid['lat_b']), max(cmpgrid['lat_b'])]
    
    # Universal plot setup
    xtick_positions = np.arange(-90,91,30)
    xticklabels = ['{}$\degree$'.format(x) for x in xtick_positions]
    ytick_positions = np.arange(0,61,20)
    yticklabels = [str(y) for y in ytick_positions]
    
    # Create pdf (if saving)
    if savepdf:
        print('\nCreating {} for {} variables'.format(pdfname, n_var))
        pdf = PdfPages(pdfname)

    # Loop over variables
    print_units_warning = True
    for ivar in range(n_var):
        if savepdf: print('{} '.format(ivar), end='')
        varname = varlist[ivar]
        
        # Do some checks: dimensions and units
        varndim_ref = refdata[varname].ndim
        varndim_dev = devdata[varname].ndim
        nlev = 72
        #assert varndim_ref == varndim_dev, 'Dimensions do not agree for {}!'.format(varname)

        units_ref = refdata[varname].units.strip()
        units_dev = devdata[varname].units.strip()
        if units_ref != units_dev:
            if print_units_warning:
                print('WARNING: ref and dev concentration units do not match!')
                print('Ref units: {}'.format(units_ref))
                print('Dev units: {}'.format(units_dev))
            if enforce_units:
            # if enforcing units, stop the program if units do not match
               assert units_ref == units_dev, 'Units do not match for {}!'.format(varname)
            else:
               # if not enforcing units, just keep going after only printing warning once 
               print_units_warning = False
               
        # Set plot extent
        extent=(-90,90,0,nlev)

        # if normalizing by area, adjust units to be per m2, and adjust title string
        units = units_ref
        varndim = varndim_ref
        subtitle_extra = ''            
        
        # Slice the data.  Need to handle different incoming number of dimensions and the bpch case
        # where no time dimension is included.

        # ref
        vdims = refdata[varname].dims
        if 'time' in vdims:
            ds_ref = refdata[varname].isel(time=itime)
        else:
            ds_ref = refdata[varname]

        # dev
        vdims = devdata[varname].dims      
        if 'time' in vdims:
            ds_dev = devdata[varname].isel(time=itime)
        else:
            ds_dev = devdata[varname]

        # if normalizing by area, transform on the native grid and adjust units and subtitle string
        exclude_list = ['WetLossConvFrac','Prod_','Loss_']
        if normalize_by_area and not any(s in varname for s in exclude_list):
            ds_ref.values = ds_ref.values / refdata['AREAM2'].values[np.newaxis,:,:]
            ds_dev.values = ds_dev.values / devdata['AREAM2'].values[np.newaxis,:,:]
            units = '{} m-2'.format(units)
            subtitle_extra = ', Normalized by Area'
   
        # Get comparison data (same grid resolution), regridding the slices if needed
        if regridref:
            ds_ref_cmp = refregridder(ds_ref)
        else:
            ds_ref_cmp = ds_ref
        if regriddev:
            ds_dev_cmp = devregridder(ds_dev)
        else:
            ds_dev_cmp = ds_dev
            
        # Calculate zonal mean of the data
        zm_ref = ds_ref.mean(dim='lon')
        zm_dev = ds_dev.mean(dim='lon')
        zm_ref_cmp = ds_ref_cmp.mean(dim='lon')
        zm_dev_cmp = ds_dev_cmp.mean(dim='lon')
            
        # Get min and max for colorbar limits
        [vmin_ref, vmax_ref] = [zm_ref.min(), zm_ref.max()]
        [vmin_dev, vmax_dev] = [zm_dev.min(), zm_dev.max()]
        [vmin_ref_cmp, vmax_ref_cmp] = [zm_ref_cmp.min(), zm_ref_cmp.max()]
        [vmin_dev_cmp, vmax_dev_cmp] = [zm_dev_cmp.min(), zm_dev_cmp.max()]
        vmin_cmp = np.min([zm_ref_cmp.min(), zm_dev_cmp.min()])
        vmax_cmp = np.max([zm_ref_cmp.max(), zm_dev_cmp.max()])
        vmin_abs = np.min([vmin_ref, vmin_dev, vmin_cmp])
        vmax_abs = np.max([vmax_ref, vmax_dev, vmax_cmp])
        if match_cbar: [vmin, vmax] = [vmin_abs, vmax_abs]
        
        # Create 2x2 figure
        figs, ((ax0, ax1), (ax2, ax3), (ax4, ax5)) = plt.subplots(3, 2, figsize=[12,15.3], 
                                                      subplot_kw={'projection': crs.PlateCarree()})
        # Give the page a title
        offset = 0.96
        fontsize=25
        figs.suptitle('{}, Zonal Mean'.format(varname), fontsize=fontsize, y=offset)

        # Subplot 0: Ref
        if not match_cbar: [vmin, vmax] = [vmin_ref, vmax_ref]
        plot0 = ax0.imshow(zm_ref, cmap=WhGrYlRd, extent=extent, vmin=vmin, vmax=vmax)
        ax0.set_title('{} (Ref){}\n{}'.format(refstr, subtitle_extra, refres ))
        ax0.set_aspect('auto')
        ax0.set_xticks(xtick_positions)
        ax0.set_xticklabels(xticklabels)
        ax0.set_yticks(ytick_positions)
        ax0.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot0, ax=ax0, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units_ref)
        
        # Subplot 1: Dev
        if not match_cbar: [vmin, vmax] = [vmin_dev, vmax_dev]
        plot1 = ax1.imshow(zm_dev, cmap=WhGrYlRd, extent=extent, vmin=vmin, vmax=vmax)
        ax1.set_title('{} (Dev){}\n{}'.format(devstr, subtitle_extra, devres ))
        ax1.set_aspect('auto')
        ax1.set_xticks(xtick_positions)
        ax1.set_xticklabels(xticklabels)
        ax1.set_yticks(ytick_positions)
        ax1.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot1, ax=ax1, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units_dev)
        
        # Calculate zonal mean difference
        zm_diff = np.array(zm_dev_cmp) - np.array(zm_ref_cmp)
                
        # Subplot 2: Difference, dynamic range
        diffabsmax = max([np.abs(zm_diff.min()), np.abs(zm_diff.max())])
        [vmin, vmax] = [-diffabsmax, diffabsmax]
        plot2 = ax2.imshow(zm_diff, cmap='RdBu_r', extent=extent, vmin=vmin, vmax=vmax)
        if regridany:
            ax2.set_title('Difference ({})\nDev - Ref, Dynamic Range'.format(cmpres))
        else:
            ax2.set_title('Difference\nDev - Ref, Dynamic Range')
        ax2.set_aspect('auto')
        ax2.set_xticks(xtick_positions)
        ax2.set_xticklabels(xticklabels)
        ax2.set_yticks(ytick_positions)
        ax2.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot2, ax=ax2, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000 or np.all(zm_diff==0):
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        if np.all(zm_diff==0): 
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])
        cb.set_label(units)
        
        # Subplot 3: Difference, restricted range
        [pct5, pct95] = [np.percentile(zm_diff,5), np.percentile(zm_diff, 95)] # placeholder: use 5 and 95 percentiles as bounds
        abspctmax = np.max([np.abs(pct5),np.abs(pct95)])
        [vmin,vmax] = [-abspctmax, abspctmax]
        plot3 = ax3.imshow(zm_diff, cmap='RdBu_r', extent=extent, vmin=vmin, vmax=vmax)
        if regridany:
            ax3.set_title('Difference ({})\nDev - Ref, Restricted Range [5%,95%]'.format(cmpres))
        else:
            ax3.set_title('Difference\nDev - Ref, Restriced Range [5%,95%]')
        ax3.set_aspect('auto')
        ax3.set_xticks(xtick_positions)
        ax3.set_xticklabels(xticklabels)
        ax3.set_yticks(ytick_positions)
        ax3.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot3, ax=ax3, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000 or np.all(zm_diff==0):
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        if np.all(zm_diff==0): 
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])
        cb.set_label(units)
        
        # Zonal mean fractional difference
        zm_fracdiff = (np.array(zm_dev_cmp) - np.array(zm_ref_cmp)) / np.array(zm_ref_cmp)
            
        # Subplot 4: Fractional Difference, dynamic range
        fracdiffabsmax = max([np.abs(zm_fracdiff.min()), np.abs(zm_fracdiff.max())])
        if np.all(zm_fracdiff == 0 ):
            [vmin, vmax] = [-2, 2]
        else:
            [vmin, vmax] = [-fracdiffabsmax, fracdiffabsmax]
        plot4 = ax4.imshow(zm_fracdiff, vmin=vmin, vmax=vmax, cmap='RdBu_r', extent=extent)
        if regridany:
            ax4.set_title('Fractional Difference ({})\n(Dev-Ref)/Ref, Dynamic Range'.format(cmpres))
        else:
            ax4.set_title('Fractional Difference\n(Dev-Ref)/Ref, Dynamic Range')
        ax4.set_aspect('auto')
        ax4.set_xticks(xtick_positions)
        ax4.set_xticklabels(xticklabels)
        ax4.set_yticks(ytick_positions)
        ax4.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot4, ax=ax4, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100 or np.all(zm_fracdiff==0):
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        if np.all(zm_fracdiff==0): 
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])
        cb.set_clim(vmin=vmin, vmax=vmax)
        cb.set_label('unitless')   
        
        # Subplot 5: Fractional Difference, restricted range
        [vmin, vmax] = [-2, 2]
        plot5 = ax5.imshow(zm_fracdiff, vmin=vmin, vmax=vmax, cmap='RdBu_r', extent=extent)
        if regridany:
            ax5.set_title('Fractional Difference ({})\n(Dev-Ref)/Ref, Fixed Range'.format(cmpres))
        else:
            ax5.set_title('Fractional Difference\n(Dev-Ref)/Ref, Fixed Range')
        ax5.set_aspect('auto')
        ax5.set_xticks(xtick_positions)
        ax5.set_xticklabels(xticklabels)
        ax5.set_yticks(ytick_positions)
        ax5.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot5, ax=ax5, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.1 or (vmax-vmin) > 100 or np.all(zm_fracdiff==0):
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        if np.all(zm_fracdiff==0): 
            cb.ax.set_xticklabels(['0.0', '0.0', '0.0', '0.0', '0.0'])
        cb.set_clim(vmin=vmin, vmax=vmax)
        cb.set_label('unitless') 
            
        if savepdf:    
            pdf.savefig(figs)
            plt.close(figs)
            
    if savepdf: pdf.close()

def compare_gchp_zonal_mean(refdata, refstr, devdata, devstr, varlist=None,
                            weightsdir='.', itime=0, llres_cmp='1x1.25', savepdf=False,
                            pdfname='gchp_vs_gchp_map.pdf', match_cbar=True, full_ratio_range=False,
                            normalize_by_area=False, area_ref=None, area_dev=None, flip_vert=False):

    # If no varlist is passed, plot all 3D variables in the dataset
    if varlist == None:
        [commonvars, commonvars2D, varlist] = compare_varnames(refdata, devdata)
        print('Plotting all 3D variables')
    n_var = len(varlist)
    
    # Get lat-lon grid
    llgrid_cmp = make_grid_LL(llres_cmp)

    # Get cubed sphere grid and regridder for first data set
    csres_ref = refdata['lon'].size
    [csgrid_ref, csgrid_list_ref] = make_grid_CS(csres_ref)
    cs_regridder_list_ref = make_regridder_C2L(csres_ref, llres_cmp, weightsdir=weightsdir, 
                                               reuse_weights=True)

    # Get cubed sphere grid and regridder for first data set
    csres_dev = devdata['lon'].size
    [csgrid_dev, csgrid_list_dev] = make_grid_CS(csres_dev)
    cs_regridder_list_dev = make_regridder_C2L(csres_dev, llres_cmp, weightsdir=weightsdir, 
                                               reuse_weights=True)
    
    # Universal plot setup
    xtick_positions = np.arange(-90,91,30)
    xticklabels = ['{}$\degree$'.format(x) for x in xtick_positions]
    ytick_positions = np.arange(0,61,20)
    yticklabels = [str(y) for y in ytick_positions]
    
    # Create pdf (if saving)
    if savepdf:
        print('\nCreating {} for {} variables'.format(pdfname, n_var))
        pdf = PdfPages(pdfname)

    # Loop over variables
    for ivar in range(n_var):
        if savepdf: print('{} '.format(ivar), end='')
        varname = varlist[ivar]
        
        # Do some checks: dimensions and units
        varndim_ref = refdata[varname].ndim
        varndim_dev = devdata[varname].ndim
        nlev = 72
        assert varndim_ref == varndim_dev, 'GCHP dimensions do not agree for {}!'.format(varname)
        units_ref = refdata[varname].units
        units_dev = devdata[varname].units
        assert units_ref == units_dev, 'GCHP units do not match for {}!'.format(varname)
        
        # Set plot extent
        extent=(-90,90,0,nlev)
        
        # if normalizing by area, adjust units to be per m2, and adjust title string
        units = units_ref
        varndim = varndim_ref
        subtitle_extra = ''
        
        # Slice the data
        vdims = refdata[varname].dims
        if 'lev' not in vdims:
            print('ERROR: variable does not have lev dimension')
            print(varname)
            return
        if 'time' in vdims:
            ds_ref = refdata[varname].isel(time=itime)
            ds_dev = devdata[varname].isel(time=itime)
        elif 'lat' in vdims and 'lon' in vdims:
            ds_ref = refdata[varname]
            ds_dev = devdata[varname]
        else:
            print('ERROR: cannot handle variables without lat and lon dimenions.')
            print(varname)
            return
            
        # if normalizing by area, transform on the native grid and adjust units and subtitle string
        exclude_list = ['WetLossConvFrac','Prod_','Loss_']
        if normalize_by_area and not any(s in varname for s in exclude_list):
            ds_ref.values = ds_ref.values / area_ref.values[np.newaxis,:,:]
            ds_dev.values = ds_dev.values / area_dev.values[np.newaxis,:,:]
            units = '{} m-2'.format(units)
            subtitle_extra = ', Normalized by Area'
            
        # Regrid the slices
        if flip_vert: 
            ds_ref.data = ds_ref.data[::-1,:,:]
            ds_dev.data = ds_dev.data[::-1,:,:]
        csdata_ref = ds_ref.data.reshape(nlev,6,csres_ref,csres_ref).swapaxes(0,1)
        csdata_dev = ds_dev.data.reshape(nlev,6,csres_dev,csres_dev).swapaxes(0,1)
        lldata_ref = np.zeros([nlev, llgrid_cmp['lat'].size, llgrid_cmp['lon'].size])
        lldata_dev = np.zeros([nlev, llgrid_cmp['lat'].size, llgrid_cmp['lon'].size])
        for i in range(6):
            regridder_ref = cs_regridder_list_ref[i]
            lldata_ref += regridder_ref(csdata_ref[i])
            regridder_dev = cs_regridder_list_dev[i]
            lldata_dev += regridder_dev(csdata_dev[i])
        
        # Calculate zonal mean of the regridded data
        zm_ref = lldata_ref.mean(axis=2)
        zm_dev = lldata_dev.mean(axis=2)
            
        # Get min and max for colorbar limits
        [vmin_ref, vmax_ref] = [zm_ref.min(), zm_ref.max()]
        [vmin_dev, vmax_dev] = [zm_dev.min(), zm_dev.max()]
        vmin_cmn = np.min([vmin_ref, vmin_dev])
        vmax_cmn = np.max([vmax_ref, vmax_dev])
        if match_cbar: [vmin, vmax] = [vmin_cmn, vmax_cmn]
        
        # Create 2x2 figure
        figs, ((ax0, ax1), (ax2, ax3)) = plt.subplots(2, 2, figsize=[12,12], 
                                                      subplot_kw={'projection': crs.PlateCarree()})
        # Give the page a title
        offset = 0.96
        fontsize=25
        figs.suptitle('{}, Zonal Mean'.format(varname), fontsize=fontsize, y=offset)

        # Subplot 0: Ref
        if not match_cbar: [vmin, vmax] = [vmin_ref, vmax_ref]
        plot0 = ax0.imshow(zm_ref, cmap=WhGrYlRd, extent=extent, vmin=vmin, vmax=vmax)
        ax0.set_title('{} (Ref){}\n{} regridded from {}'.format(refstr, subtitle_extra, 
                                                                llres_cmp, csres_ref))
        ax0.set_aspect('auto')
        ax0.set_xticks(xtick_positions)
        ax0.set_xticklabels(xticklabels)
        ax0.set_yticks(ytick_positions)
        ax0.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot0, ax=ax0, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot 1: Dev
        if not match_cbar: [vmin, vmax] = [vmin_dev, vmax_dev]
        plot1 = ax1.imshow(zm_dev, cmap=WhGrYlRd, extent=extent, vmin=vmin, vmax=vmax)
        ax1.set_title('{} (Dev){}\n{} regridded from {}'.format(devstr, subtitle_extra, 
                                                                llres_cmp, csres_dev))
        ax1.set_aspect('auto')
        ax1.set_xticks(xtick_positions)
        ax1.set_xticklabels(xticklabels)
        ax1.set_yticks(ytick_positions)
        ax1.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot1, ax=ax1, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
            
        # Subplot 2: Difference
        zm_absdiff = zm_dev - zm_ref
        diffabsmax = max([np.abs(zm_absdiff.min()), np.abs(zm_absdiff.max())])
        [vmin, vmax] = [-diffabsmax, diffabsmax]
        plot2 = ax2.imshow(zm_absdiff, cmap='RdBu_r', extent=extent, vmin=vmin, vmax=vmax)
        ax2.set_title('Difference\n(Dev - Ref)')
        ax2.set_aspect('auto')
        ax2.set_xticks(xtick_positions)
        ax2.set_xticklabels(xticklabels)
        ax2.set_yticks(ytick_positions)
        ax2.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot2, ax=ax2, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot 3: Fractional Difference (restrict to +/-2)
        zm_fracdiff = (zm_dev - zm_ref) / zm_ref
        if full_ratio_range: [vmin, vmax] = [None, None]
        else: [vmin, vmax] = [-2, 2]
        plot3 = ax3.imshow(zm_fracdiff, vmin=vmin, vmax=vmax, cmap='RdBu_r', extent=extent)
        ax3.set_title('Fractional Difference\n(Dev - Ref)/Ref')
        ax3.set_aspect('auto')
        ax3.set_xticks(xtick_positions)
        ax3.set_xticklabels(xticklabels)
        ax3.set_yticks(ytick_positions)
        ax3.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot3, ax=ax3, orientation='horizontal', pad=0.10)
        cb.set_clim(vmin=vmin, vmax=vmax)
        cb.set_label('unitless')      
            
        if savepdf:    
            pdf.savefig(figs)
            plt.close(figs)
            
    if savepdf: pdf.close()
    
def add_bookmarks_to_pdf( pdfname, varlist, remove_prefix='' ):
    # Existing pdf
    pdfobj = open(pdfname,"rb")
    input = PdfFileReader(pdfobj)
    numpages = input.getNumPages()
    
    # Pdf write and new filename
    pdfname_tmp = pdfname+'_with_bookmarks.pdf'
    output = PdfFileWriter()
    
    # Loop over variables (pages) in the file, removing the diagnostic prefix
    varnamelist = [k.replace(remove_prefix,'') for k in varlist]
    for i, varname in enumerate(varnamelist):
        output.addPage(input.getPage(i))
        output.addBookmark(varname,i)
        output.setPageMode('/UseOutlines')
        
    # Write to new file
    outputstream = open(pdfname_tmp,'wb')
    output.write(outputstream) 
    outputstream.close()
    
    # Replace the old file with the new
    os.rename(pdfname_tmp, pdfname)

def add_hierarchical_bookmarks_to_pdf( pdfname, catdict, remove_prefix='' ):
    # Existing pdf
    pdfobj = open(pdfname,"rb")
    input = PdfFileReader(pdfobj)
    numpages = input.getNumPages()
    
    # Pdf write and new filename
    pdfname_tmp = pdfname+'_with_bookmarks.pdf'
    output = PdfFileWriter()
    
    # Loop over variables (pages) in the file, removing the diagnostic prefix
    varnamelist = [k.replace(remove_prefix,'') for k in varlist]
    for i, varname in enumerate(varnamelist):
        output.addPage(input.getPage(i))
        output.addBookmark(varname,i)
        output.setPageMode('/UseOutlines')
        
    # Write to new file
    outputstream = open(pdfname_tmp,'wb')
    output.write(outputstream) 
    outputstream.close()
    
    # Replace the old file with the new
    os.rename(pdfname_tmp, pdfname)


def compare_gchp_vs_gcc_zonal_mean(dgcc, dgchp, varlist=None, weightsdir='.', itime=0, llres_raw='4x5', 
                       llres_cmp='1x1.25', savepdf=False, pdfname='gchp_vs_gcc_map.pdf', match_cbar=True, 
                       full_ratio_range=False, normalize_by_area=False, area1=None, area2=None,
                      flip_vert=False):

    # If no varlist is passed, plot all 3D variables in the dataset
    if varlist == None:
        [commonvars, commonvars2D, varlist] = compare_varnames(dgcc, dgchp)
        print('Plotting all 3D variables')
    n_var = len(varlist)
    
    # Get lat-lon grids and regridder. Assume regridding weights have already been generated
    llgrid_raw = make_grid_LL(llres_raw)
    llgrid_cmp = make_grid_LL(llres_cmp)
    ll_regridder = make_regridder_L2L(llres_raw, llres_cmp, weightsdir=weightsdir, reuse_weights=True)

    # Get cubed sphere grid and regridder
    csres = dgchp['lon'].size
    [csgrid, csgrid_list] = make_grid_CS(csres)
    cs_regridder_list = make_regridder_C2L(csres, llres_cmp, weightsdir=weightsdir, reuse_weights=True)
    
    # Universal plot setup
    xtick_positions = np.arange(-90,91,30)
    xticklabels = ['{}$\degree$'.format(x) for x in xtick_positions]
    ytick_positions = np.arange(0,61,20)
    yticklabels = [str(y) for y in ytick_positions]
    
    # Create pdf (if saving)
    if savepdf:
        print('\nCreating {} for {} variables'.format(pdfname, n_var))
        pdf = PdfPages(pdfname)

    # Loop over variables
    for ivar in range(n_var):
        if savepdf: print('{} '.format(ivar), end='')
        varname = varlist[ivar]
        
        # Do some checks: dimensions and units
        varndim = dgchp[varname].ndim
        varndim2 = dgcc[varname].ndim
        if 'ilev' in dgcc[varname].dims: nlev = 73
        else: nlev = 72
        assert varndim == varndim2, 'GCHP and GCC dimensions do not agree for {}!'.format(varname)
        units_raw = dgchp[varname].units
        units2 = dgcc[varname].units
        assert units_raw == units2, 'GCHP and GCC units do not match for {}!'.format(varname)
        
        # Set plot extent
        extent=(-90,90,0,nlev)
        
        # if normalizing by area, adjust units to be per m2, and adjust title string
        units = units_raw
        subtitle_extra = ''
         
        # Slice the data
        ds1 = dgcc[varname].isel(time=itime)
        ds2 = dgchp[varname].isel(time=itime)

        # if normalizing by area, transform on the native grid and adjust units and subtitle string
        exclude_list = ['WetLossConvFrac','Prod_','Loss_']
        if normalize_by_area and not any(s in varname for s in exclude_list):
            ds1.values = ds1.values / area1.values[np.newaxis,:,:]
            ds2.values = ds2.values / area2.values[np.newaxis,:,:]
            units = '{} m-2'.format(units_raw)
            subtitle_extra = ', Normalized by Area'
            
        # Regrid the slices
        if flip_vert: ds2.data = ds2.data[::-1,:,:]
        csdata = ds2.data.reshape(nlev,6,csres,csres).swapaxes(0,1)
        gchp_ll = np.zeros([nlev, llgrid_cmp['lat'].size, llgrid_cmp['lon'].size])
        for i in range(6):
            regridder = cs_regridder_list[i]
            gchp_ll += regridder(csdata[i])
        gcc_ll = ll_regridder(ds1)
        
        # Calculate zonal mean of the regridded data
        gchp_zm = gchp_ll.mean(axis=2)
        gcc_zm = gcc_ll.mean(axis=2)
            
        # Get min and max for colorbar limits
        [vmin_gchp, vmax_gchp] = [gchp_zm.min(), gchp_zm.max()]
        [vmin_gcc, vmax_gcc] = [gcc_zm.min(), gcc_zm.max()]
        vmin_cmn = np.min([vmin_gchp, vmin_gcc])
        vmax_cmn = np.max([vmax_gchp, vmax_gcc])
        if match_cbar: [vmin, vmax] = [vmin_cmn, vmax_cmn]
        
        # Create 2x2 figure
        figs, ((ax0, ax1), (ax2, ax3)) = plt.subplots(2, 2, figsize=[12,12], 
                                                      subplot_kw={'projection': crs.PlateCarree()})
        # Give the page a title
        offset = 0.96
        fontsize=25
        figs.suptitle('{}, Zonal Mean'.format(varname), fontsize=fontsize, y=offset)

        # Subplot 0: GCHP regridded
        if not match_cbar: [vmin, vmax] = [vmin_gchp, vmax_gchp]
        plot0 = ax0.imshow(gchp_zm, cmap=WhGrYlRd, extent=extent, vmin=vmin, vmax=vmax)
        ax0.set_title('GCHP Regridded{}\n{}'.format(subtitle_extra, llres_cmp))
        ax0.set_aspect('auto')
        ax0.set_xticks(xtick_positions)
        ax0.set_xticklabels(xticklabels)
        ax0.set_yticks(ytick_positions)
        ax0.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot0, ax=ax0, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot 1: GCC regridded
        if not match_cbar: [vmin, vmax] = [vmin_gcc, vmax_gcc]
        plot1 = ax1.imshow(gcc_zm, cmap=WhGrYlRd, extent=extent, vmin=vmin, vmax=vmax)
        ax1.set_title('GCC Regridded{}\n{}'.format(subtitle_extra, llres_cmp))
        ax1.set_aspect('auto')
        ax1.set_xticks(xtick_positions)
        ax1.set_xticklabels(xticklabels)
        ax1.set_yticks(ytick_positions)
        ax1.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot1, ax=ax1, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
            
        # Subplot 2: Difference
        gc_absdiff = gchp_zm - gcc_zm
        diffabsmax = max([np.abs(gc_absdiff.min()), np.abs(gc_absdiff.max())])
        [vmin, vmax] = [-diffabsmax, diffabsmax]
        plot2 = ax2.imshow(gc_absdiff, cmap='RdBu_r', extent=extent, vmin=vmin, vmax=vmax)
        ax2.set_title('Difference\n(GCHP - GCC)')
        ax2.set_aspect('auto')
        ax2.set_xticks(xtick_positions)
        ax2.set_xticklabels(xticklabels)
        ax2.set_yticks(ytick_positions)
        ax2.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot2, ax=ax2, orientation='horizontal', pad=0.10)
        if (vmax-vmin) < 0.001 or (vmax-vmin) > 1000:
            cb.locator = ticker.MaxNLocator(nbins=4)
            cb.update_ticks()
        cb.set_label(units)
        
        # Subplot 3: Fractional Difference (restrict to +/-2)
        gc_fracdiff = (gchp_zm - gcc_zm) / gcc_zm
        if full_ratio_range: [vmin, vmax] = [None, None]
        else: [vmin, vmax] = [-2, 2]
        plot3 = ax3.imshow(gc_fracdiff, vmin=vmin, vmax=vmax, cmap='RdBu_r', extent=extent)
        ax3.set_title('Fractional Difference\n(GCHP-GCC)/GCC')
        ax3.set_aspect('auto')
        ax3.set_xticks(xtick_positions)
        ax3.set_xticklabels(xticklabels)
        ax3.set_yticks(ytick_positions)
        ax3.set_yticklabels(yticklabels)
        cb = plt.colorbar(plot3, ax=ax3, orientation='horizontal', pad=0.10)
        cb.set_clim(vmin=vmin, vmax=vmax)
        cb.set_label('unitless')      
            
        if savepdf:    
            pdf.savefig(figs)
            plt.close(figs)
            
    if savepdf: pdf.close()
