# =======================================================================================
# =======================================================================================

import numpy as np
import sys
import getopt
import code  # For development: code.interact(local=locals())
from datetime import datetime
from matplotlib.dates import date2num, num2date
import csv
from scipy.io import netcdf
#import matplotlib
#matplotlib.use('Agg')
import matplotlib.pyplot as plt

# =======================================================================================
# Parameters
# =======================================================================================

simple_verify_ts = True
epsilon          = 0.622       # Ratio of gas constants vapor/dry air [g/g]
e_0              = 0.611       # saturation vapor pressure at 0C Clausius-Clapeyron [kPa]
L_vap            = 2.5*10.0**6 # Latent heat of vaporization [J/kg]
R_vap            = 461.0       # gas constant for water vapor [J/Kg/K]
T_0              = 273.0       # Temperature at freezing point of water [K]
d_per_mo         = [31,28,31,30,31,30,31,31,30,31,30,31]  # Days per month (NO LEAP YEAR)


# =======================================================================================
# Classes and Types
# =======================================================================================

class ctrltype:    

    # This holds control parameter specified in XML
    
    def __init__(self,csv_file,time_res_sec_in,time_res_sec_out,n_header_row,n_fields, \
                 nodata_flags,grid_name_out,fill_value,missing_value, \
                 acknowledge,history,date_format,time_format):

        self.csv_file         = csv_file
        self.time_res_sec_in  = time_res_sec_in
        self.time_res_sec_out = time_res_sec_out
        self.n_header_row     = n_header_row
        self.n_fields         = n_fields
        self.nodata_flags  = nodata_flags
        self.grid_name_out = grid_name_out
        self.fill_value    = fill_value
        self.missing_value = missing_value
        self.acknowledge   = acknowledge
        self.history       = history
        self.date_format   = date_format
        self.time_format   = time_format

class contype:    

    # This holds constants specified in XML (Like Lat/lon)

    def __init__(self,name,long_name,units,mode,value,dims):
        
        self.name      = name
        self.long_name = long_name
        self.units     = units
        self.mode      = mode
        self.value     = float(value)
        self.dims      = int(dims)

class vartype:    
    
    # This holds time dependent variables specified in XML/CSV (like temp,etc)

    def __init__(self,name,long_name,units,mode,col_id,unit_mult,unit_off):
    
        self.name      = name
        self.long_name = long_name
        self.units     = units
        self.mode      = mode
        self.col_id    = col_id
        self.unit_mult = unit_mult
        self.unit_off  = unit_off

    def alloc_raw(self,nraw):

        self.datavec = np.zeros((nraw))


class timetype:   
    
    # This is time, like the thing that always goes forward and cant be seen
    # or touched, insert creative riddle here

    def __init__(self,ntimes):
    
        self.year  = -9*np.ones((ntimes))
        self.month = -9*np.ones((ntimes))
        # This is a floating point decimal day
        self.day   = -9.0*np.ones((ntimes))

        # This is a decimal datenumber
        self.datenum = -9.0*np.ones((ntimes))

    def setbounds(self):

        self.yeara  = int(self.year[0])
        self.montha = int(self.month[0])
        self.yearz  = int(self.year[-1])
        self.monthz = int(self.month[-1])


# =======================================================================================
# Non class subroutines
# =======================================================================================

def rh100_to_qsat_kgkg(RH100,P_kpa,T_k):
    
    # Convert relative humidity as a percent into specific humidity in kg/kg
    # via Clausius-Clapeyron equation for saturation specific humidity

    # rh100:  relative humidity  [%]
    # T:      Temperature        [K]
    # P:      Air Pressure       [kPa]

    # Saturation Vapor Pressure via Clausius-Clapeyron  [kPa]
    e_sat = e_0 * np.exp( L_vap/R_vap * (1.0/T_0 - 1.0/T_k) )

    # Saturation Specific Humidity [kg/kg]
    q_sat = epsilon * e_sat / P_kpa
    
    # RH100/100.0 = q/q_sat
    q = np.min([100.0,RH100])*q_sat/100.0

    return(q)

def VPD_to_RH(VPD,P_kpa,T_k):
    e_sat = e_0 * np.exp( L_vap/R_vap * (1.0/T_0 - 1.0/T_k) )
    RH = (1-VPD/e_sat)*100
    return(RH)

def fillvar_convert_units(variables,textarray,idx): 

    # Fills the variables and converts units from csv to desired units
    #
    # Most of the unit changes can be accomodated by offsets and multipliers
    # But some conversions may depend on lapse rates, if reference heights are
    # dissimilar (not implemented), or conversion from relative to specific humidity.
    # These will determined via flaogs.

    
    for var in variables:

        # First, parse the unit multipliers and offsets to strings
        umul_vec  = var.unit_mult.strip().split(',')
        uoff_vec  = var.unit_off.strip().split(',')
        colid_vec = var.col_id.strip().split(',')

        # Special Case 1, VPD to RH to specific humidity in [kg/kg]
        
        if( (var.name == 'QBOT') ):

            if(len(uoff_vec) != 3 | len(umul_vec) !=3 | len(colid_vec) != 3):
                print('Incorrect multiplier, offset or col_id specification')
                print('on conversion from relative to specific humidity?')
                print('-1 offset flag triggers Clausius-Clapeyron conversion')
                print('and its expected to have 3 arguments: the first is -1')
                print('the next two, comma delimted are offsets for Pressure')
                print('and temperature')
                print('You must also specify the columns of RH,P and T in col_id')
                print('respectively, as well.')
                exit(2)

            # Assumption, convert RH to SH
            VPD = float(textarray[int(colid_vec[0])-1]) * float(umul_vec[0])
            #RH100 = float(textarray[int(colid_vec[0])-1]) * float(umul_vec[0]) # OFFSET IS FLAG 
            P_kpa = float(textarray[int(colid_vec[1])-1]) * float(umul_vec[1]) + float(uoff_vec[1])
            T_k   = float(textarray[int(colid_vec[2])-1]) * float(umul_vec[2]) + float(uoff_vec[2])

            # Saturation Specific Humidity [kg/kg]
            RH = VPD_to_RH(VPD,P_kpa,T_k)
            q_spec = rh100_to_qsat_kgkg(RH,P_kpa,T_k)

            var.datavec[idx] = q_spec
        elif( (var.name == 'RH') ):
            VPD = float(textarray[int(colid_vec[0])-1]) * float(umul_vec[0])
            P_kpa = float(textarray[int(colid_vec[1])-1]) * float(umul_vec[1]) + float(uoff_vec[1])
            T_k   = float(textarray[int(colid_vec[2])-1]) * float(umul_vec[2]) + float(uoff_vec[2])
            RH = VPD_to_RH(VPD,P_kpa,T_k)
            var.datavec[idx] = RH
            # In all other cases, the multiplier and offset should be sufficient
        else:
            var.datavec[idx] = float(textarray[int(colid_vec[0])-1]) * float(umul_vec[0]) + float(uoff_vec[0])

        


# =======================================================================================

def load_xml(xmlfile):
    
    import xml.etree.ElementTree as et

    print('Interpreting XML File')

    constants = []
    variables = []
    
    xmlroot = et.parse(xmlfile).getroot()
    
    for elem in xmlroot.iter('constant'):
        name      = elem.find('name').text.strip()
        long_name = elem.find('long_name').text.strip()
        units     = elem.find('units').text.strip()
        mode      = elem.find('mode').text.strip()
        value     = float(elem.find('value').text)
        dims      = int(elem.find('dims').text.strip())
        constants.append(contype(name,long_name,units,mode,value,dims))

    # Some variables may have multiple specifications for the offsets
    # and multipliers, which in those cases, they are acting as flags
    # because multiple arguments are needed for conversions (eg rh->sh)
    for elem in xmlroot.iter('variable'):
        name      = elem.find('name').text.strip()
        long_name = elem.find('long_name').text.strip()
        units     = elem.find('units').text.strip() 
        mode      = elem.find('mode').text.strip()
        col_id    = elem.find('col_id').text       # Store as strings (might be vector)
        unit_mult = elem.find('unit_mult').text    # Store as strings
        unit_off  = elem.find('unit_off').text     # Store as strings
        variables.append(vartype(name,long_name,units,mode,col_id,unit_mult,unit_off))
    
    csv_file      = xmlroot.find('csv_file').text.strip()
    time_res_sec_in  = float(xmlroot.find('input_time_resolution').text)
    time_res_sec_out = float(xmlroot.find('output_time_resolution').text)
    n_header_row  = int(xmlroot.find('n_header_row').text)
    date_format   = xmlroot.find('date_format').text.strip()
    time_format   = xmlroot.find('time_format').text.strip()
    n_fields      = int(xmlroot.find('n_fields').text)
    nodata_flags  = xmlroot.find('nodata_flags').text.strip()
    grid_out_name = xmlroot.find('grid_name_out').text.strip()
    fill_value    = xmlroot.find('fill_value_out').text.strip()
    missing_value = xmlroot.find('missing_value_out').text.strip()
    acknowledge   = xmlroot.find('acknowledgements').text
    history       = xmlroot.find('history').text


    ctrl_params=ctrltype(csv_file,time_res_sec_in,time_res_sec_out,n_header_row,n_fields,nodata_flags,   \
                         grid_out_name,fill_value,missing_value,acknowledge,history, \
                         date_format,time_format)


    return(constants,variables,ctrl_params)

# =======================================================================================

def usage():
     print('')
     print('=======================================================================')
     print('')
     print(' python ConvertMetCSVtoCLMALM.py -h --f=<xml-file-name>')
     print('')
     print('')
     print(' -h --help ')
     print('     print this help message')
     print('')
     print('')
     print(' --f=<xml-file-name>')
     print('     This is the full path to the XML file that describes the conversion')
     print('     The default packaged with this script is convert_controls.xml')
     print('')
     print('')
     print('=======================================================================')

def interp_args(argv):

    argv.pop(0)  # The script itself is the first argument, forget it

    # Name of the conversion file
    xmlfile = "none"

    try:
        opts, args = getopt.getopt(argv, 'h',["f="])

    except getopt.GetoptError as err:
        print('Argument error, see usage')
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit(0)
        elif o in ("--f"):
            xmlfile = a
        else:
            assert False, "unhandled option"


    if (xmlfile == "none"):
        print("You must specify an xml file, see usage:")
        usage()
        sys.exit(2)


    return (xmlfile)


# =======================================================================================

def load_csv(ctrlp,variables):

    print('Loading the CSV data into memory & converting units')

    nlines = 0
    with open(ctrlp.csv_file, 'rU') as csvfile:
        
        csvfile.seek(ctrlp.n_header_row)
        csvreader = csv.reader(csvfile,  dialect=csv.excel_tab, delimiter=',')
#        csvreader = csv.reader(open(csvfile, 'rU'), dialect=csv.excel_tab)
        for row in csvreader:
            nlines+=1

        nlines-=ctrlp.n_header_row

        # Allocate raw data
        for var in variables:
            var.alloc_raw(nlines)

        # Allocate timing data
        rawtime = timetype(nlines)

        # Load raw data
        csvfile.seek(0)
        csvreader = csv.reader(csvfile,  dialect=csv.excel_tab, delimiter=',')
        
        iidx=0
        for idx,rowtext in enumerate(csvreader):
            #print("rowtext = {a}".format(a=rowtext))
            if (idx>=ctrlp.n_header_row):

                # Transfer CSV data in, convert units as well
                
                fillvar_convert_units(variables,rowtext,iidx)
                #print("updatedRowText? = {a}\n".format(a=rowtext))
                # Timing information
                date_str1 = rowtext[0]
                date_str2 = rowtext[1]
                #print("str1: {a}\tstr2: {b}".format(a=rowtext[0], b=rowtext[1]))
                #date1,time1 = date_str1.split(' ')
                #date2,time2 = date_str2.split(' ')

                #if(ctrlp.date_format == 'Y-M-D'):
                #    yr1,mo1,dy1 = date1.split('-')
                #    yr2,mo2,dy2 = date2.split('-')
                #elif(ctrlp.date_format == 'M/D/Y'):
                #    mo1,dy1,yr1 = date1.split('/')
                #    mo2,dy2,yr2 = date2.split('/')
                #else:
                #print('Incorectly specified date_format')
                #print('\nAttempting correct time format...')
                #exit(2)
                yr1=date_str1[:4]
                yr2=date_str2[:4]
                mo1=date_str1[4:6]
                mo2=date_str2[4:6]
                dy1=date_str1[6:8]
                dy2=date_str2[6:8]
                hr1=date_str1[8:10]
                hr2=date_str2[8:10]
                mn1=date_str1[10:12]
                mn2=date_str2[10:12]
                sec1=0
                sec2=0 #data isn't this detailed I believe
     	        #if(ctrlp.time_format == 'H:M'):
                #    hr1,mn1 = time1.split(':')
                #    hr2,mn2 = time2.split(':')
                #elif(ctrlp.time_format == 'H:M:S'):
                #    hr1,mn1,sec1 = time1.split(':')
                #    hr2,mn2,sec2 = time2.split(':')
                #else:
                #print('Incorectly specified time_format')
                #print('\nShould be correct, actually')
		#exit(2)

                iyr1 = int(yr1)
                iyr2 = int(yr2)

                if(iyr1<50):
                    iyr1 +=2000
                if(iyr2<50):
                    iyr2 +=2000

                t1 = date2num(datetime(iyr1,int(mo1),int(dy1),int(hr1),int(mn1)))
                #print("{a}, {b}, {c}, {d}, {e}".format(a=iyr2, b=mo2, c=dy2, d=hr2, e=mn2))
                t2 = date2num(datetime(iyr2,int(mo2),int(dy2),int(hr2),int(mn2)))

                teff = np.mean([t1,t2])
                #teff = date2num(datetime(int(yr1),int(mo1),int(dy1),int(hr1),int(mn1)+30))

                datestamp = num2date(teff)

                rawtime.datenum[iidx] = teff
                rawtime.year[iidx]  = datestamp.year
                rawtime.month[iidx] = datestamp.month
                rawtime.day[iidx]   = float(datestamp.day) + \
                                      float(datestamp.hour)/24.0 + \
                                      float(datestamp.minute)/1440.0 + \
                                      float(datestamp.second)/86400.0
#                rawtime.day[iidx] = (float(datestamp.day)-1.0)*86400.0 + \
#                                    float(datestamp.hour)*3600.0 + \
#                                    float(datestamp.minute)*60.0 + \
#                                    float(datestamp.second)
                iidx+=1

    # Perform some visualization checks if this is turned on
    if(simple_verify_ts):
#        code.interact(local=locals())
        for var in variables:
            print("{c}".format(c=var.name))
#            plt.plot_date(rawtime.datenum,var.datavec)
#            plt.plot_date(rawtime.datenum[24280:32000],var.datavec[24280:32000])
#            code.interact(local=locals())
#            plt.title(var.name)
#            plt.ylabel(var.units)
#            plt.xlabel('Date') 
#            plt.show()
            
        # Check the time variability
#        plt.plot(rawtime.datenum[0:-2]-rawtime.datenum[1:-1])
#        plt.show()
        

    return(variables,rawtime)

# ========================================================================================
# ========================================================================================
#                                        Main
# ========================================================================================
# ========================================================================================

def main(argv):

    # Interpret the arguments to the script
    xmlfile = interp_args(argv)
    
    constants,variables,ctrl_params = load_xml(xmlfile)

    

    # Algorithm:

    # 1) Loop through file and load data
    # 2) Determine set of complete months
    # 3) Loop through set of complete months
    # 4) Read in lines, parse data, convert where necessary

    # 1)
    variables,timing = load_csv(ctrl_params,variables)

    # 2) Set max/min timing info
    timing.setbounds()

    # 4) Loop output files and write

    print('Writing data to netcdf files')
    for iyr in range(timing.yeara,timing.yearz+1):
        if(iyr == timing.yeara):
            ima = timing.montha
        else:
            ima = 1
        if(iyr == timing.yearz):
            imz = timing.monthz
        else:
            imz = 12

        for imo in range(ima,imz+1):

            ncfilename = ctrl_params.grid_name_out+'{:04d}'.format(iyr)+"-"+'{:02d}'.format(imo)+".nc"
            print('Preparing: '+ncfilename)

            if(imo==12):
                imo_end = 1
                iyr_end = iyr+1
                idy_end = 1
                ihr_end = 0
                imn_end = 0
            elif(imo==2):
                imo_end = 2
                iyr_end = iyr
                idy_end = 28
                ihr_end = 23
                imn_end = 59
            else:
                imo_end = imo+1
                iyr_end = iyr
                idy_end = 1

            datenum_a = date2num(datetime(int(iyr),int(imo),int(1)))
            datenum_b = date2num(datetime(int(iyr),int(imo),int(d_per_mo[int(imo)-1]),int(23),int(59)))

            # Find all the time-points betwixt
            ids = np.where((timing.datenum>=datenum_a) & (timing.datenum<datenum_b))[0]

            # Open the netcdf file
            fp = netcdf.netcdf_file(ncfilename, 'w')

            fp.acknowledgements = ctrl_params.acknowledge
            fp.history          = ctrl_params.history

#            code.interact(local=locals())

            # Create an averaged data vector if the input versus output
            # resolution is different
            n_hr_out = ctrl_params.time_res_sec_out/3600.0
            
            ntime = d_per_mo[int(imo)-1]*24.0/float(n_hr_out)

            if( ntime != float(int(ntime)) ):
                print('Poorly specified output frequency')
                print('Must generate an even number of time-points per day')
                exit(2)

            ntime = int(ntime)
            day_of_month = []
            for itime in range(int(ntime)):
                decimal_day = float(itime)*(float(ctrl_params.time_res_sec_out)/86400.0)
                day_of_month.append(decimal_day)

            fp.createDimension('time',ntime)
            fp.createDimension('lon',1)
            fp.createDimension('lat',1)
            fp.createDimension('scalar',1)
            
            time_out    = fp.createVariable('time','f8',('time',))
            time_out[:] = day_of_month[:]
            time_out.units = 'days since {:04d}'.format(iyr)+'-{:02d}-01 00:00:00'.format(imo)
            time_out.calendar = 'noleap'
            time_out.long_name = 'observation time'

            for var in variables:

                datavec_out  = []
                for itime in range(int(ntime)):
                    decimal_day_a = float(itime)*(float(ctrl_params.time_res_sec_out)/86400.0)
                    decimal_day_b = float(itime+1)*(float(ctrl_params.time_res_sec_out)/86400.0)
                    iday_a = int(np.floor(decimal_day_a))+1
                    iday_b = int(np.floor(decimal_day_b))+1
                    ihr_a  = np.mod(int(itime*n_hr_out),24)
                    ihr_b  = np.mod(int((itime+1)*n_hr_out),24)
                    imin_a = int(round(60.0*( 24.0*(decimal_day_a+1.0-float(iday_a)) - float(ihr_a)),0))
                    imin_b = int(round(60.0*( 24.0*(decimal_day_b+1.0-float(iday_b)) - float(ihr_b)),0))
                    imo_b = imo
                    iyr_b = iyr
                    if(iday_b > d_per_mo[int(imo)-1]):
                        iday_b = 1
                        imo_b  = imo+1
                        if(imo_b>12):
                            imo_b = 1
                            iyr_b = iyr+1
                            #print("{}-{}-{} {}:{} to {}-{}-{} {}:{}".format(iyr,imo,iday_a,ihr_a,imin_a,iyr_b,imo_b,iday_b,ihr_b,imin_b))
                    datenum_a = date2num(datetime(int(iyr),int(imo),iday_a,ihr_a,int(imin_a)))
                    datenum_b = date2num(datetime(int(iyr_b),int(imo_b),iday_b,ihr_b,int(imin_b)))
                    ids = np.where((timing.datenum>=datenum_a) & (timing.datenum<datenum_b))[0]
                    if(len(ids)==0):
                        print('No time records were found in an anticipated window.')
                        print("{}-{}-{} {}:{} to {}-{}-{} {}:{}".format(iyr,imo,iday_a,ihr_a,int(imin_a),iyr,imo,iday_b,ihr_b,int(imin_b)))
                        exit(2)

                    datavec_out.append(float(np.mean( var.datavec[ids] )))

                var_out = fp.createVariable(var.name,'f8',('time','lat','lon'))
                var_out[:,0,0] = datavec_out
                var_out.units = var.units
                var_out.long_name = var.long_name
                var_out.mode = var.mode
                print("{a}, {b}".format(a=var.name, b=np.average(var_out[:,0,0])))
                fp.flush()

            for const in constants:

                if(const.dims == 1):
                    const_out = fp.createVariable(const.name,'f8',('scalar',))
                    const_out.assignValue(float(const.value))
                    const_out.units = const.units
                    const_out.long_name = const.long_name
                    const_out.mode = const.mode
                    fp.flush()

                elif(const.dims == 2):
                    const_out = fp.createVariable(const.name,'f8',('lat','lon'))
                    const_out.assignValue(const.value)
                    const_out.units = const.units
                    const_out.long_name = const.long_name
                    const_out.mode = const.mode
                    fp.flush()

                else:
                    print('Undefined dimension spec for constants')
                    print('dims must be 1: scalar or 2: lat x lon')
                    exit(2)


            fp.close()

    print('Conversion from CSV to ELM/CLM format complete!')
    exit(0)




# =======================================================================================
# This is the actual call to main
   
if __name__ == "__main__":
    main(sys.argv)








