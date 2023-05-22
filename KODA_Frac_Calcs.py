import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.linear_model import LinearRegression
import datetime as dt
from tkinter import filedialog as fd
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from os.path import exists
import csv
import os
import subprocess

# Plot treatment pressure, slurry rate, open well head pressure, and initial and final isip for one stage
def full_frac_plot(i,owp,initial_isip,final_isip,root):
    fig = plt.Figure(figsize=(9, 6), dpi=100)
    ax1 = fig.add_subplot(111)
    line = FigureCanvasTkAgg(fig, root)
    line.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH)
    ax1.plot(stage_data[i].index,stage_data[i]['Treating_Pressure'],label='Treating Pressure')
    ax1.set_ylabel('Pressure (psi)')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.set_xlabel('Time (HH:MM)')
    ax1.tick_params(axis='x', labelrotation = 45)
    
    ax1.axhline(owp,linestyle='dashed',label='Open well Head Pressure',color='green')
    ax1.axhline(initial_isip,linestyle='dashed',label='Initial ISIP',color='purple')
    ax1.axhline(final_isip,linestyle='dashed',label='Final ISIP',color='cyan')

    ax2 = ax1.twinx()
    ax2.plot(stage_data[i].index,stage_data[i]['Blender_Slurry_Rate'],color='red',label='Slurry Rate')
    y_b,y_t = ax2.get_ylim()
    if y_t < 5:
        ax2.set_ylim(bottom=0,top=5)
    else:
        ax2.set_ylim(bottom=0)
    ax2.set_ylabel('Slurry Rate (bpm)')
    
    lns = ax1.lines + ax2.lines
    labs = [l.get_label() for l in lns]
    
    ax1.set_title('Stage ' + str(i))
    plt.tight_layout()
    ax1.legend(lns, labs, loc='center left', bbox_to_anchor=(1,1))
    fig.subplots_adjust(right=.72)
    
    #Create a user interface to display plot and relevant data
    t_text = 'Well: ' + str(api) + ' ' + str(well) + ' Stage ' + str(i)\
        + '\nThe open well head pressure is ' + str(f'{round(owp):,}') + ' psig'\
           '\nThe initial isip is ' + str(f'{round(i_isip[s]):,}') + ' psig'\
           '\nThe final isip is ' + str(f'{round(f_isip[s]):,}') + 'psig'
    
    # Create a label widget for custom text
    text_label = tk.Label(root, text=t_text, anchor='w')
    text_label.pack(fill='both')

    # Create buttons widget for to either move to next graph or skip all graphs
    next_button = tk.Button(root, text="Next", command=next_stage)
    next_button.pack()

    skip_all_button = tk.Button(root, text="Skip All", command=skip_all)
    skip_all_button.pack()

    x = 100
    y = 100
    root.geometry('+%d+%d'%(x,y))  
    root.mainloop()

def next_stage():
    root.destroy()
    
def skip_all():
    global skip
    skip = 1
    root.destroy()
        
def flag1(stage_data,i):
    #Determine the initial pressure and flag after 10 psi increase or decrease
    init_p = stage_data['Treating_Pressure'].iloc[0]
    idx1 = ((stage_data['Treating_Pressure'] >= init_p + 10) | (stage_data['Treating_Pressure'] <= init_p - 10)).idxmax()

    return idx1

def flag3(stage_data,i):
    #Flag first occurence of blender slurry rate above 0.5 bpd
    idx3 = (stage_data['Blender_Slurry_Rate'] >= 0.5).idxmax()

    return idx3

def flag2(stage_data,i):
    #Slice stage dataset between Flag 1 and Flag 3
    f1_to_f3 = stage_data.loc[idxs['1'][i]:idxs['3'][i]].copy()

    #Create a new dataframe containing the second-to-second treating presure change
    tp_change = pd.DataFrame({'tp_change':np.diff(f1_to_f3['Treating_Pressure'])
                                 ,'time_stamp':f1_to_f3.index[:-1]})

    #Trim last 10 seconds and flag all occurences of treating pressure change greater than 10 psi
    f2 = pd.DataFrame(tp_change[:-10])
    f2['tp_flag'] = 0
    f2.loc[f2['tp_change']>10,'tp_flag'] = 1

    #Reverse f2 so we can find the first occurence of p_change = 1
    f2 = f2.reindex(index=f2.index[::-1])

    f2id_1 = (f2['tp_flag'] == 1).idxmax()
    f2id_2 = f2.iloc[0].name

    #Get time stamp of Flag 2 and Flag 3 minus 10 seconds
    idx2 = f2.loc[f2id_1,'time_stamp']
    idx3_a = f2.loc[f2id_2,'time_stamp']
    open_well_pressure = stage_data['Treating_Pressure'].loc[idx2:idx3_a].mean()

    return idx2, idx3_a, open_well_pressure

def flag4(stage_data,i):
    #Flag first occurence of blender slurry rate below 0.5 bpd after Flag 3
    idx4 = ((stage_data['Blender_Slurry_Rate'] <= 0.5) & (stage_data.index > idxs['3'][i])).idxmax()

    return idx4

def flag5(stage_data,i):
    #Flag first occurence of blender slurry rate above 0.5 bpd after Flag 4
    idx5 = ((stage_data['Blender_Slurry_Rate'] >= 0.5) & (stage_data.index > idxs['4'][i])).idxmax()

    return idx5

def flag6(stage_data,i):
    #Reverse the index of the stage data to find the last occurence of slurry rate above 0.5 bpd

    f6 = stage_data.reindex(index=stage_data.index[::-1])
    idx6 = (f6['Blender_Slurry_Rate'] >= 0.5).idxmax()
    
    return idx6

def flag7(stage_data,i):
    #Slice stage dataset between Flag 6 and the end
    f6_to_end = stage_data.loc[idxs['6'][i]:].copy()

    #Create a new dataframe containing the second-to-second treating presure change and plot
    tp_change = pd.DataFrame({'tp_change':np.diff(f6_to_end['Treating_Pressure'])
                                 ,'time_stamp':f6_to_end.index[:-1]})

    #Find the minimum pressure change value. Subtract 15 seconds from this and assign as Flag 7
    f7id = np.argmin(tp_change['tp_change'])
    idx7 = tp_change.loc[f7id-15,'time_stamp']

    return idx7

def init_isip(stage_data,i):
    
    #Slice stage 1 dataset between Flag 4 and Flag 5
    f4_to_f5 = stage_data.loc[idxs['4'][i]:idxs['5'][i]].copy()

    #Calculate the change in slurry rate and restrict data set to first and last occurence of no change
    sl_change = pd.DataFrame({'sl_change':np.diff(f4_to_f5['Blender_Slurry_Rate'])
                                 ,'time_stamp':f4_to_f5.index[:-1]})

    sl_change_rev = sl_change.reindex(index=sl_change.index[::-1])

    idx4_a = sl_change.loc[(sl_change['sl_change'] == 0).idxmax() + 1,'time_stamp']
    idx5_a = sl_change.loc[(sl_change_rev['sl_change'] == 0).idxmax() - 1,'time_stamp']

    #Set up and perform a regression on the trimmed dataset
    X_date = pd.Series(stage_data[idx4_a:idx5_a].index)
    X = X_date.apply(lambda x: x.timestamp()).values.reshape(-1,1)

    y = stage_data[idx4_a:idx5_a]['Treating_Pressure']
    
    reg = LinearRegression().fit(X,y)
    
    y_pred = reg.predict(X)
    isip_init = y_pred[0]
                              
    return idx4_a, idx5_a, isip_init

def final_isip(stage_data,i):
    #Slice stage 1 dataset between Flag 6 and Flag 7
    f6_to_f7 = stage_data.loc[idxs['6'][s]:idxs['7'][s]].copy()

    #Calculate the change in slurry rate and restrict data set to first and last occurence of no change
    sl_change = pd.DataFrame({'sl_change':np.diff(f6_to_f7['Blender_Slurry_Rate'])
                                 ,'time_stamp':f6_to_f7.index[:-1]})

    sl_change_rev = sl_change.reindex(index=sl_change.index[::-1])

    idx6_a = sl_change.loc[(sl_change['sl_change'] == 0).idxmax() + 1,'time_stamp']
    idx7_a = sl_change.loc[(sl_change_rev['sl_change'] == 0).idxmax() - 1,'time_stamp']

    #Set up and perform a regression on the trimmed dataset
    X_date = pd.Series(stage_data[idx6_a:idx7_a].index)
    X = X_date.apply(lambda x: x.timestamp()).values.reshape(-1,1)

    y = stage_data[idx6_a:idx7_a]['Treating_Pressure']

    reg = LinearRegression().fit(X,y)

    y_pred = reg.predict(X)
    isip_final = y_pred[0]
    
    return idx6_a, idx7_a, isip_final

def add_bad_stage(well,stage,bad_stages):
    t = 'Stage ' + str(stage)
    if well in bad_stages:
        bad_stages[well].append(t)
    else:
        bad_stages[well] = [t]
        
    return bad_stages

#__________________________________________________________________________
#Start main script
root = tk.Tk()
root.withdraw()
file_s = fd.askopenfilenames(title='Select frac data file(s) to analyze',
                          filetypes = [('csv', '*.csv')]  )
root.destroy()
skip = 0
first = 0
j = 0

for f in file_s:
    #Import data and convert to datetime
    frac_data = pd.read_csv(f)
    cols = ['Time','Net_Pressure_Time','Stage_Counter','Blender_Slurry_Rate','Treating_Pressure','API','WELL_NAME','STAGE_NUMBER']
    frac_data = frac_data[cols].copy()
    frac_data['Time'] = pd.to_datetime(frac_data['Time'])
    frac_data.set_index('Time',inplace=True)
    well = frac_data['WELL_NAME'][0]
    api = frac_data['API'][0]

    #Create a dictionary containing each stage as a dataframe
    stage_data = {}
    stages = frac_data['STAGE_NUMBER'].unique()
    sorted_stages = []

    for i in range(stages.min(),stages.max()+1):
        df = frac_data[frac_data['STAGE_NUMBER']==i].copy()
        df.sort_index(inplace=True)
        stage_data[i] = df[~df.index.duplicated(keep='first')]
        sorted_stages.append(i)
    
    #Create a dictionary to store flags for each stage, open well head pressure, and initial and final isip.
    #Create a list to store bad stages where flag values are not sequential.
    idxs = {'1':{},
        '2':{},
        '3':{},
        '3a':{},
        '4':{},
        '4a':{},
        '5':{},
        '5a':{},
        '6':{},
        '6a':{},
        '7':{},
        '7a':{}}
    owp = {}
    i_isip = {}
    f_isip = {}
    bad_stages = {}
    
    #Find each flag for a stage. Check if the flags are in sequential order before continuing.
    #If flags are not sequential then skip that stage and alert the user.
    for s in sorted_stages:
        idxs['1'][s] = flag1(stage_data[s],s)
        idxs['3'][s] = flag3(stage_data[s],s)
        if idxs['3'][s] < idxs['1'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
            
        idxs['2'][s],idxs['3a'][s], owp[s] = flag2(stage_data[s],s)
        if ((idxs['2'][s] < idxs['1'][s]) | (idxs['3a'][s] < idxs['2'][s])):
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
        
        idxs['4'][s] = flag4(stage_data[s],s)
        if idxs['4'][s] < idxs['3'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
        
        idxs['5'][s] = flag5(stage_data[s],s)
        if idxs['5'][s] < idxs['4'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
            
        idxs['6'][s] = flag6(stage_data[s],s)
        if idxs['6'][s] < idxs['5'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
        
        idxs['7'][s] = flag7(stage_data[s],s)
        if idxs['7'][s] < idxs['6'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
                    
        idxs['4a'][s], idxs['5a'][s], i_isip[s] = init_isip(stage_data[s],s)
        if idxs['5a'][s] < idxs['4a'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
            
        idxs['6a'][s], idxs['7a'][s], f_isip[s] = final_isip(stage_data[s],s)
        if idxs['7a'][s] < idxs['6a'][s]:
            bad_stages = add_bad_stage(well,s,bad_stages)
            continue
        
        if skip == 0:
            root = tk.Tk()
            full_frac_plot(s,owp[s],i_isip[s],f_isip[s],root)
    
    #Create a screen to show which stages were not calculated if the skip button has not been pushed
    if skip == 0:
        root = tk.Tk()
        t_text = ''
        for element in bad_stages[well]:
            if t_text:
                t_text = t_text + ',\n' + str(element)
            else:
                t_text = 'The following stages could not be automatically calculated for well '\
                + str(well) + ' ' + str(api) + ':\n' + str(element)
        
        # Create a label widget for custom text
        text_label = tk.Label(root, text=t_text, anchor='w')
        text_label.pack(fill='both')
        
        # Create buttons widget for to either move to next graph or skip all graphs
        next_button = tk.Button(root, text="Next", command=next_stage)
        next_button.pack()
        
        x = 500
        y = 150
        root.geometry('+%d+%d'%(x,y))
        root.mainloop()
    
    #Write frac calcs to csv
    for s in sorted_stages:
        stage = 'Stage ' + str(s)
        fieldnames = ['Well','API','Stage','OWP','Initial ISIP','Final ISIP']
        if j == 1:
            with open('frac_calcs.csv', 'a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)

                # write a new row to the CSV file
                if stage in bad_stages[well]:
                    writer.writerow({'Well':well,'API':api,'Stage':s,'OWP':'N/A','Initial ISIP':'N/A','Final ISIP':'N/A'})
                else:
                    writer.writerow({'Well':well,'API':api,'Stage':s,'OWP':round(owp[s]),'Initial ISIP':round(i_isip[s]),'Final ISIP':round(f_isip[s])})
        
        else:
            with open('frac_calcs.csv', 'w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                # write a new row to the CSV file
                if stage in bad_stages[well]:
                    writer.writerow({'Well':well,'API':api,'Stage':s,'OWP':'N/A','Initial ISIP':'N/A','Final ISIP':'N/A'})
                else:
                    writer.writerow({'Well':well,'API':api,'Stage':s,'OWP':round(owp[s]),'Initial ISIP':round(i_isip[s]),'Final ISIP':round(f_isip[s])})
        j = 1

if os.name == 'nt':
    os.startfile('frac_calcs.csv')
else:
    subprocess.call(('open','frac_calcs.csv'))

exit()