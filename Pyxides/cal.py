from Pyxis import *

import ms
import mqt
import imager

# register ourselves with Pyxis, and define what superglobals we use
register_pyxis_module(superglobals="MS DDID LSM FIELD");

# various tools
# Note that default arguments are interpolated when the tool is actually invoked
remove		= xo.rm.args("-fr");
copy		= x.cp.args("-a");
plotparms       = x("plot-parms.py").args("$PLOTPARMS_ARGS");
flagms          = x("flag-ms.py")
mergems         = x("merge-ms.py");
downweigh       = x("downweigh-redundant-baselines.py")
fitstool        = x("fitstool.py")
tigger_restore  = x("tigger-restore")
tigger_convert  = x("tigger-convert")
tigger_tag      = x("tigger-tag")
aoflagger       = x.aoflagger
addbitflagcol   = x.addbitflagcol
wsrt_j2convert  = x.wsrt_j2convert

## default scripts
SIM_SCRIPT = "turbo-sim.py"


SELFCAL_SCRIPT  = "calico-wsrt-tens.py"

## MS_TDL: this gets passed to TDL scripts to specify an MS
## use this version when MSs have true DDIDs set
#MS_TDL_Template='ms_sel.msname=$MS ms_sel.ddid_index=$DDID ms_sel.field_index=$FIELD'
## use this version when MSs have DDID=0 for all bands
MS_TDL_Template = 'ms_sel.msname=$MS ms_sel.ddid_index=$DDID ms_sel.field_index=$FIELD'
# LSM selection
LSM_TDL_Template='tiggerlsm.filename=$LSM'

# destination directory for plots, images, etc.
DESTDIR_Template = 'plots-spw${DDID}${-stage<STAGE}'
# base filename for these files
OUTFILE_Template = '${DESTDIR>/}${MS:BASE}${_spw<DDID}${_s<STEP}${_<LABEL}'

## runtime globals

## channel range, as (start,end[,step]), or list of such tuples per DDID, or None for all
CHANRANGE = None

## current spwid and number of channels. Note that these are set automatically from the MS by the _msddid_Template below
SPWID = 0
TOTAL_CHANNELS = 0

## whenever the MS or DDID changes, look up the corresponding info on channels and spectral windows 
_msddid = None;
def _msddid_Template ():
  global SPWID,TOTAL_CHANNELS,_ms_ddid;
  if (MS,DDID) != _msddid and MS and DDID is not None:
    try:
      SPWID = ms.ms(MS,"DATA_DESCRIPTION").getcol("SPECTRAL_WINDOW_ID",DDID,1)[0];
      TOTAL_CHANNELS = ms.ms(MS,"SPECTRAL_WINDOW").getcol("NUM_CHAN",SPWID,1)[0];
      # make sure this is reevaluated
      _chanspec_Template();
      info("$MS ddid $DDID is spwid $SPWID with $TOTAL_CHANNELS channels"); 
    except:
      return None;
  return MS,DDID;

## whenever the channel range changes, setup strings for TDL & Owlcat channel selection (CHAN_TDL and CHAN_OWLCAT),
## and also CHANSTART,CHANSTEP,NUMCHANS
_chanspec = None;
def _chanspec_Template ():
  global CHAN_TDL,CHAN_OWLCAT,CHANSTART,CHANSTEP,NUMCHANS;
  chans = CHANRANGE;
  if isinstance(CHANRANGE,(list,tuple)) and type(CHANRANGE[0]) is not int:
    chans = CHANRANGE[DDID];
  # process channel specification 
  if chans is None:
    CHAN_OWLCAT = '';
    CHANSTART,CHANSTEP,NUMCHANS = 0,1,TOTAL_CHANNELS;
    CHAN_TDL = 'ms_sel.select_channels=0';
  else:
    if type(chans) is int:
      CHANSTART,CHANSTEP,NUMCHANS = chans,1,1;
    elif len(chans) == 1:
      CHANSTART,CHANSTEP,NUMCHANS = chans[0],1,1;
    elif len(chans) == 2:
      CHANSTART,CHANSTEP,NUMCHANS = chans[0],1,(chans[1]-chans[0]+1);
    elif len(chans) == 3:
      CHANSTART,CHANSTEP,NUMCHANS = chans[0],chans[2],(chans[1]-chans[0]+1);
    CHAN_OWLCAT = "-L %d~%d:%d"%(CHANSTART,CHANSTAR+NUMCHANS-1,CHANSTEP);
    CHAN_TDL = 'ms_sel.select_channels=1 ms_sel.ms_channel_start=%d ms_sel.ms_channel_end=%d ms_sel.ms_channel_step=%d'%chans;
  return CHANSTART,CHANSTEP,NUMCHANS;

## set this to zero to skip MS plots
PLOTVIS = "CORRECTED_DATA:I"

## extra TDL options passed to any script
EXTRA_TDLOPTS = ""

## optional step and stage counters, plus an operation label. These can be used in e.g. output filenames
STEP = 1
STAGE = ""
LABEL = ""

# filenames for images
DIRTY_IMAGE_Template = "${OUTFILE}.dirty.fits"
RESTORED_IMAGE_Template = "${OUTFILE}.restored.fits"
RESIDUAL_IMAGE_Template = "${OUTFILE}.residual.fits"
MODEL_IMAGE_Template = "${OUTFILE}.model.fits"
FULLREST_IMAGE_Template = "${OUTFILE}.fullrest.fits"

# How to channelize the output image. 0 for average all, 1 to include all, 2 to average with a step of 2, etc.
# None means defer to 'imager' module options
IMAGE_CHANNELIZE = None
# passed to tigger-restore when restoring models into images. Use e.g. "-b 45" for a 45" restoring beam.
RESTORING_OPTIONS = ""
# default clean algorithm
CLEAN_ALGORITHM="clark";

def _make_destdir ():
  if not os.path.exists(DESTDIR):
    os.mkdir(DESTDIR);

def make_image (msname="$MS",column="CORRECTED_DATA",dirty=True,restore=False,channelize=None,lsm="$LSM",config="",**kw0):
  """Makes image(s) from MS. Set dirty and restore to True or False to make the appropriate images. You can also
  set either to a dict of options to be passed to the imager. If restore=True and 'lsm' is set, it will also make 
  a full-restored image (i.e. will restore the LSM into the image) with tigger-restore. Use this when deconvolving 
  residual images. Note that RESTORING_OPTIONS are passed to tigger-restore.
  
  'config' specifies a config file for run-imager. If empty, the default imager.conf is used.
  
  'channelize', if set, overrides the IMAGE_CHANNELIZE setting. If both are None, the options in the 'imager' module take effect. 
  
  Image names are determined by the globals DIRTY_IMAGE, RESTORED_IMAGE, RESIDUAL_IMAGE, MODEL_IMAGE and FULLREST_IMAGE"""
  msname,column,lsm = interpolate_locals("msname column lsm"); 
  _make_destdir();
  
  # setup imager options
  kw0.update(dict(chanstart=CHANSTART,chanstep=CHANSTEP,nchan=NUMCHANS));
  if channelize is None:
    channelize = IMAGE_CHANNELIZE;
  if channelize == 0:
    kw0.update(img_nchan=1,img_chanstart=CHANSTART,img_chanstep=CHANSTEP);
  elif channelize > 0:
    kw0.update(img_nchan=NUMCHANS//channelize,img_chanstart=CHANSTART,img_chanstep=channelize);
    
  kw0.update(ms=msname,data=column);

  if dirty:
    info("Making dirty image DIRTY_IMAGE=$DIRTY_IMAGE");
    kw = kw0.copy();
    if type(dirty) is dict:
      kw.update(dirty);
    imager.run(operation="image",image=DIRTY_IMAGE,**kw);
    v.IMAGE = DIRTY_IMAGE;
  if restore:
    info("Making restored image RESTORED_IMAGE=$RESTORED_IMAGE");
    info("       (MODEL_IMAGE=$MODEL_IMAGE RESIDUAL_IMAGE=$RESIDUAL_IMAGE)");
    kw = kw0.copy();
    if type(restore) is dict:
      kw.update(restore);
    imager.run(operation=CLEAN_ALGORITHM,restored=RESTORED_IMAGE,model=MODEL_IMAGE,residual=RESIDUAL_IMAGE,**kw)
    v.IMAGE = RESTORED_IMAGE;
    if lsm:
      info("Restoring LSM into FULLREST_IMAGE=$FULLREST_IMAGE");
      tigger_restore("$RESTORING_OPTIONS","-f",RESTORED_IMAGE,lsm,FULLREST_IMAGE);
      v.IMAGE = FULLREST_IMAGE;


STEFCAL_SCRIPT  = "calico-stefcal.py"
STEFCAL_SECTION = "stefcal"
STEFCAL_JOBNAME = "_tdl_job_1_StefCal"
STEFCAL_TDLOPTS = ""
STEFCAL_IFRGAINS = "ifrgains.cp"
STEFCAL_IFRGAINS_SAVE_Template = "$OUTFILE.ifrgains.cp"
      
def stefcal ( msname="$MS",section="$STEFCAL_SECTION",label="G",
              reset_ifrgains=False,
              diffgains=None,
              plotvis="$PLOTVIS",
              dirty=True,restore=False,
              args=[],options={},
              **kws):
  """Generic function to run a stefcal job.
  
  'section'         is config file section
  'label'           will be assigned to the global LABEL for purposes of file naming
  'reset_ifrgains'  reset IFR gain solutions before starting
  'diffgains'       set to a source subset string to solve for diffgains. Set to True to use "=dE"
  'plotvis'	    plot output visibilities using plot-ms
  'dirty','restore' image output visibilities (passed to make_image above as is)
  'args','options'  passed to the stefcal job as is, can be used to supply extra TDL options
  """;
  msname,section,lsm,LABEL,plotvis = interpolate_locals("msname section lsm label plotvis");
  _make_destdir();
  
  # increment step counter
  global STEP
  if type(STEP) is int:
    STEP += 1;

  # remove saved gains if asked to 
  if os.path.exists(STEFCAL_IFRGAINS) and reset_ifrgains:
    remove(STEFCAL_IFRGAINS);
    
  # setup stefcal options and run 
  info("Running stefcal ${step <STEP} ${(<LABEL>)}");
  args = list(args);
  args.append("$MS_TDL $CHAN_TDL $LSM_TDL $EXTRA_TDLOPTS de_subset.subset_enabled=%d"%(1 if diffgains else 0));
  if diffgains:
    if diffgains is True:
      diffgains = "=dE";
    args.append("de_subset.source_subset=$diffgains"); 
  mqt.run(STEFCAL_SCRIPT,STEFCAL_JOBNAME,section=section,args=args,options=options);
  
  # copy gains
  if os.path.exists(STEFCAL_IFRGAINS):
    copy(STEFCAL_IFRGAINS,STEFCAL_IFRGAINS_SAVE);

  # plot residuals
  if plotvis:
    info("Plotting visibilities ($plotvis)");
    ms.plotms(msname,plotvis,CHAN_OWLCAT,"-o ${OUTFILE}_residuals${_s<step}${_<label}.png");
    
  # make images
  make_image(msname,dirty=dirty,restore=restore);
  

PYBDSM_OUTPUT_Template = "${OUTFILE}_pybdsm.lsm.html"    
PYBDSM_POLARIZED = 0
_pybdsm = x.pybdsm;

def pybdsm_search (image="$RESTORED_IMAGE",threshold=None,output="$PYBDSM_OUTPUT",pol=None,**kw):
  image,output = interpolate_locals("image output");
  # setup parameters
  script = II("${output:BASE}.pybdsm");
  srl = II("${output:BASE}.srl");
  if threshold:
    kw['thresh_isl'] = kw['thresh_pix'] = threshold;
  kw['polarisation_do'] = pol = bool(PYBDSM_POLARIZED if pol is None else pol);
  # join args into one string which can be passed to process_image(), and run the program
  args = ",".join([ "%s=%s"%kv for kv in kw.iteritems() ]);
  file(script,"w").write(II("""process_image(filename='$image',$args)\n"""+
     "write_catalog(outfile='$srl',clobber=True)\nquit"));
  _pybdsm(stdin=file(script));
  tigger_convert(srl,output,"-t","ASCII","--format",
    "name Isl_id ra_d E_RA dec_d E_DEC i E_Total_flux Peak_flux E_Peak_flux "+
    "RA_max E_RA_max DEC_max E_DEC_max Maj E_Maj Min E_Min PA E_PA "+
    "emaj_d E_DC_Maj emin_d E_DC_Min pa_d E_DC_PA Isl_Total_flux E_Isl_Total_flux "+
    "Isl_rms Isl_mean Resid_Isl_rms Resid_Isl_mean S_Code " +
    ("q E_Total_Q u E_Total_U v E_Total_V Linear_Pol_frac Elow_Linear_Pol_frac Ehigh_Linear_Pol_frac "+
     "Circ_Pol_Frac Elow_Circ_Pol_Frac Ehigh_Circ_Pol_Frac Total_Pol_Frac Elow_Total_Pol_Frac Ehigh_Total_Pol_Frac Linear_Pol_Ang E_Linear_Pol_Ang"
    if pol else ""),
    "-f","--rename",split_args=False);


def transfer_tags (fromlsm,lsm="$LSM",tags="dE",tolerance=60*ARCSEC):
  fromlsm,lsm,tags = interpolate_locals("fromlsm lsm tags");
  # now, set dE tags on sources
  import Tigger
  refmodel = Tigger.load(fromlsm);
  model = Tigger.load(lsm);
  tagset = frozenset(tags.split(" "));
  info("Transferring tags %s from %s to %s"%(",".join(tagset),fromlsm,lsm));
  # for each dE-tagged source in the reference model, find all nearby sources
  # in our LSM, and tag them
  for src0 in refmodel.getSourceSubset(",".join(["="+x for x in tagset])):
    for src in model.getSourcesNear(src0.pos.ra,src0.pos.dec,tolerance=tolerance):
      for tag in tagset:
        tagval = src0.getTag(tag,None);
        if tagval is not None:
          src.setTag("dE",True);
        info("setting tag %s on source %s (from reference source %s)"%(tag,src.name,src0.name))
  model.save(lsm)
                                