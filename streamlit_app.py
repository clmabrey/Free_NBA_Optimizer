import pulp
import numpy as np
import pandas as pd
import random
import sys
import openpyxl
import re
import time
import streamlit as st
import matplotlib
from  matplotlib.colors import LinearSegmentedColormap
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode

st.set_page_config(layout="wide")

tab1, tab2 = st.tabs(["Projections", "Optimizer"])

lineup_display = []
check_list = []
rand_player = 0
boost_player = 0
salaryCut = 0

CSV_URL = 'https://sheetdb.io/api/v1/5e6ksfq0q1ghr?sheet=DK_CSV'

@st.cache
def convert_df_to_csv(df):
  # IMPORTANT: Cache the conversion to prevent computation on every rerun
  return df.to_csv().encode('utf-8')

@st.experimental_memo
def grab_csv_data(URL):
    draftkings_data = pd.read_json(URL)
    draftkings_data.rename(columns={"Name": "Player"}, inplace = True)
    
    return draftkings_data

with tab1:
    hold_container = st.empty()
    st.info('This is a free to use NBA optimizer for Clockwork Sports NBA DFS users. In order to use it, upload a csv with that the columns oriented in this order: Player, Team, Position, Salary, Projection, Ownership. The columns names do not matter, but the orientation does!')
    uploaded_file = st.file_uploader("Choose a file")
    if uploaded_file is not None:
      proj_data = pd.read_csv(uploaded_file)
      proj_data = proj_data.replace(',','', regex=True)
      st.write(proj_data)
        
with tab2:   
    col1, col2 = st.columns([1, 4])
    
    with col1:
      
        max_sal = st.number_input('Max Salary', min_value = 35000, max_value = 50000, value = 50000, step = 100)
        min_sal = st.number_input('Min Salary', min_value = 35000, max_value = 49900, value = 49000, step = 100)
        proj_cut = st.number_input('Lowest median allowed', min_value = 0, max_value = 25, value = 10, step = 1)
        slack_var = st.number_input('Median randomness', min_value = 0, max_value = 5, value = 0, step = 1)
        totalRuns_raw = st.number_input('How many Lineups', min_value = 1, max_value = 1000, value = 5, step = 1)

    totalRuns = totalRuns_raw
    cut_group_1 = []
    cut_group_2 = []
    force_group_1 = []
    force_group_2 = []
    avoid_players = []
    lock_player = []
    lineups = []
    player_pool_raw = []
    
    player_pool = []
    player_count = []
    player_trim_pool = []
    portfolio = pd.DataFrame()
    x = 1

    if st.button('Optimize'):
        max_proj = 1000
        max_own = 1000
        total_proj = 0
        total_own = 0
        
        with col2:
            with st.spinner('Wait for it...'):
                with hold_container.container():

                        while x <= totalRuns:

                            raw_proj_file = proj_data
                            raw_proj_file.columns = ['Player', 'Team', 'Position', 'Salary', 'Median', 'Own']
                            raw_proj_file = raw_proj_file.replace(',','', regex=True)
                            raw_flex_file = raw_proj_file.dropna(how='all')
                            raw_flex_file['Salary'] = raw_flex_file['Salary'].astype(float)
                            raw_flex_file = raw_flex_file.loc[raw_flex_file['Median'] > 0]
                            raw_flex_file = raw_flex_file.loc[raw_flex_file['Median'] > proj_cut]
                            flex_file = raw_flex_file
                            flex_file = flex_file[['Player', 'Team', 'Position', 'Salary', 'Median', 'Own']]
                            flex_file.rename(columns={"Position": "Pos", "Own": "Proj DK Own%"}, inplace = True)
                            flex_file['name_var'] = flex_file['Player']
                            flex_file['lock'] = flex_file['Player'].isin(lock_player)*1
                            flex_file['force_group_1'] = flex_file['Player'].isin(force_group_1)*1
                            flex_file['force_group_2'] = flex_file['Player'].isin(force_group_2)*1
                            flex_file['cut_group_1'] = flex_file['Player'].isin(cut_group_1)*1
                            flex_file['cut_group_2'] = flex_file['Player'].isin(cut_group_2)*1
                            chalk_file = flex_file.sort_values(by='Proj DK Own%', ascending=False)
                            chalk_group_df = chalk_file.sample(n=10)
                            chalk_group = chalk_group_df['Player'].tolist()
                            flex_file['chalk_group'] = flex_file['Player'].isin(chalk_group)*1
                            flex_file = flex_file[['Player', 'name_var', 'Team', 'Pos', 'Salary', 'Median', 'Proj DK Own%', 'lock', 'force_group_1', 'force_group_2', 'cut_group_1', 'cut_group_2', 'chalk_group']]
                            if x > 1:
                                if slack_var > 0:
                                    flex_file['randNumCol'] = np.random.randint(-int(slack_var),int(slack_var), flex_file.shape[0])
                                elif slack_var ==0:
                                    flex_file['randNumCol'] = 0
                            elif x == 1:
                                flex_file['randNumCol'] = 0
                            flex_file['Median'] = flex_file['Median'] + flex_file['randNumCol']
                            flex_file_check = flex_file
                            player_ids = flex_file.index
                            
                            overall_players = flex_file[['Player']]
                            overall_players['player_var_add'] = flex_file.index
                            overall_players['player_var'] = 'player_vars_' + overall_players['player_var_add'].astype(str)
                            
                            csv_data = grab_csv_data(CSV_URL)
                            csv_merge = pd.merge(csv_data, flex_file, how='left', left_on=['Player'], right_on = ['Player'])
                            id_dict = dict(zip(csv_merge['Player'], csv_merge['Name + ID']))
                            
                            player_vars = pulp.LpVariable.dicts("player_vars", flex_file.index, 0, 1, pulp.LpInteger)
                            total_score = pulp.LpProblem("Fantasy_Points_Problem", pulp.LpMaximize)
                            player_match = dict(zip(overall_players['player_var'], overall_players['Player']))
                            player_index_match = dict(zip(overall_players['player_var'], overall_players['player_var_add']))
                            player_own = dict(zip(flex_file['Player'], flex_file['Proj DK Own%']))
                            player_sal = dict(zip(flex_file['Player'], flex_file['Salary']))
                            player_proj = dict(zip(flex_file['Player'], flex_file['Median']))
                            pos_dict = dict(zip(flex_file['Player'], flex_file['Pos']))

                            obj_points = {idx: (flex_file['Median'][idx]) for idx in flex_file.index}
                            total_score += sum([player_vars[idx]*obj_points[idx] for idx in flex_file.index])

                            obj_points_max = {idx: (flex_file['Median'][idx]) for idx in flex_file.index}
                            obj_own_max = {idx: (flex_file['Proj DK Own%'][idx]) for idx in flex_file.index}

                            obj_salary = {idx: (flex_file['Salary'][idx]) for idx in flex_file.index}
                            total_score += pulp.lpSum([player_vars[idx]*obj_salary[idx] for idx in flex_file.index]) <= max_sal
                            total_score += pulp.lpSum([player_vars[idx]*obj_salary[idx] for idx in flex_file.index]) >= min_sal

                            if len(lock_player) > 0:
                                for flex in flex_file['lock'].unique():
                                    sub_idx = flex_file[flex_file['lock'] == 1].index
                                    total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) == len(lock_player)

                            if len(force_group_1) > 0:
                                for flex in flex_file['force_group_1'].unique():
                                    sub_idx = flex_file[flex_file['force_group_1'] == 1].index
                                    total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            if len(force_group_2) > 0:
                                for flex in flex_file['force_group_2'].unique():
                                    sub_idx = flex_file[flex_file['force_group_2'] == 1].index
                                    total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            if len(cut_group_1) > 0:
                                for flex in flex_file['cut_group_1'].unique():
                                    sub_idx = flex_file[flex_file['cut_group_1'] == 1].index
                                    total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 1

                            if len(cut_group_2) > 0:
                                for flex in flex_file['cut_group_2'].unique():
                                    sub_idx = flex_file[flex_file['cut_group_2'] == 1].index
                                    total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 1
                                    
                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("PG")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("SG")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("SF")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("PF")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("C")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 1

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("C")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("G")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 3    

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'].str.contains("F")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 3

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'].str.contains("F")) | (flex_file['Pos'].str.contains("C"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'] == ("PG")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 3

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'] == ("SG")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 3

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'] == ("SF")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 3

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'] == ("PF")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 3

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'] == ("C")].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 2

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'] == ("PF/C")) | (flex_file['Pos'] == ("C")) | (flex_file['Pos'] == ("PF")) | (flex_file['Pos'] == ("SF/PF"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) >= 2

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'] == ("PG")) | (flex_file['Pos'] == ("C"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'] == ("SG")) | (flex_file['Pos'] == ("C"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'] == ("SF")) | (flex_file['Pos'] == ("C"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'] == ("PF")) | (flex_file['Pos'] == ("C"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[(flex_file['Pos'].str.contains("PF")) | (flex_file['Pos'] == ("C"))].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) <= 4

                            for flex in flex_file['Pos'].unique():
                                sub_idx = flex_file[flex_file['Pos'] != "Var"].index
                                total_score += pulp.lpSum([player_vars[idx] for idx in sub_idx]) == 8

                            player_count = []
                            player_trim = []
                            lineup_list = []

                            total_score += pulp.lpSum([player_vars[idx]*obj_points_max[idx] for idx in flex_file.index]) <= max_proj - .01

                            total_score.solve()
                            for v in total_score.variables():
                                if v.varValue > 0:
                                    lineup_list.append(v.name)
                            df = pd.DataFrame(lineup_list)
                            df['Names'] = df[0].map(player_match)
                            df['Cost'] = df['Names'].map(player_sal)
                            df['Proj'] = df['Names'].map(player_proj)
                            df['Own'] = df['Names'].map(player_own)
                            total_cost = sum(df['Cost'])
                            total_own = sum(df['Own'])
                            total_proj = sum(df['Proj'])
                            lineup_raw = pd.DataFrame(lineup_list)
                            lineup_raw['Names'] = lineup_raw[0].map(player_match)
                            lineup_raw['value'] = lineup_raw[0].map(player_index_match)
                            lineup_final = lineup_raw.sort_values(by=['value'])
                            del lineup_final[lineup_final.columns[0]]
                            del lineup_final[lineup_final.columns[1]]
                            lineup_final = lineup_final.reset_index(drop=True)
                            lineup_test = lineup_final
                            lineup_final = lineup_final.T
                            lineup_final['Cost'] = total_cost
                            lineup_final['Proj'] = total_proj
                            lineup_final['Own'] = total_own

                            if total_cost < 50001:
                                lineups.append(lineup_final)
                            
                            lineup_test['Salary'] = lineup_test['Names'].map(player_sal)
                            lineup_test['Proj'] = lineup_test['Names'].map(player_proj)
                            lineup_test['Own'] = lineup_test['Names'].map(player_own)
                            lineup_test.loc['Column_Total'] = lineup_test.sum(numeric_only=True, axis=0)
                            
                            lineup_display.append(lineup_test)
                            
                            with col2:
                                with st.container():
                                    st.table(lineup_test)

                            max_proj = total_proj
                            max_own = total_own

                            check_list.append(total_proj)

                            portfolio = portfolio.append(lineup_final, ignore_index = True)

                            x += 1
                        
                        portfolio.rename(columns={0: "Player", 1: "Player", 2: "Player", 3: "Player", 4: "Player", 5: "Player", 6: "Player", 7: "Player"}, inplace = True)
                        portfolio = portfolio.dropna()

                        final_outcomes = portfolio
                        final_outcomes.columns = ['Player', 'Player.1', 'Player.2', 'Player.3', 'Player.4', 'Player.5', 'Player.6', 'Player.7', 'Cost', 'Proj', 'Own']

                        final_outcomes['pos.1'] = final_outcomes['Player'].map(pos_dict)
                        final_outcomes['pos.2'] = final_outcomes['Player.1'].map(pos_dict)
                        final_outcomes['pos.3'] = final_outcomes['Player.2'].map(pos_dict)
                        final_outcomes['pos.4'] = final_outcomes['Player.3'].map(pos_dict)
                        final_outcomes['pos.5'] = final_outcomes['Player.4'].map(pos_dict)
                        final_outcomes['pos.6'] = final_outcomes['Player.5'].map(pos_dict)
                        final_outcomes['pos.7'] = final_outcomes['Player.6'].map(pos_dict)
                        final_outcomes['pos.8'] = final_outcomes['Player.7'].map(pos_dict)

                        final_positions = final_outcomes[['pos.1','pos.2','pos.3','pos.4','pos.5','pos.6','pos.7','pos.8']]

                        final_outcomes['PG-count'] = final_positions.apply(lambda x: x.str.contains("PG").sum(), axis=1)
                        final_outcomes['SG-count'] = final_positions.apply(lambda x: x.str.contains("SG").sum(), axis=1)
                        final_outcomes['SF-count'] = final_positions.apply(lambda x: x.str.contains("SF").sum(), axis=1)
                        final_outcomes['PF-count'] = final_positions.apply(lambda x: x.str.contains("PF").sum(), axis=1)
                        final_outcomes['C-count'] = final_positions.apply(lambda x: x.str.contains("C").sum(), axis=1)
                        final_outcomes['two_c'] = final_positions.apply(lambda x: x.str.fullmatch("C").sum(), axis=1)
                        final_outcomes['two_pg'] = final_positions.apply(lambda x: x.str.fullmatch("PG").sum(), axis=1)
                        final_outcomes['two_sg'] = final_positions.apply(lambda x: x.str.fullmatch("SG").sum(), axis=1)
                        final_outcomes['two_sf'] = final_positions.apply(lambda x: x.str.fullmatch("SF").sum(), axis=1)
                        final_outcomes['two_pf'] = final_positions.apply(lambda x: x.str.fullmatch("PF").sum(), axis=1)
                        final_outcomes['SG/SF'] = final_positions.apply(lambda x: x.str.match("SG/SF").sum(), axis=1)
                        final_outcomes['SF/PF'] = final_positions.apply(lambda x: x.str.match("SF/PF").sum(), axis=1)
                        final_outcomes['PG_hard'] = final_positions.apply(lambda x: x.str.fullmatch("PG").sum(), axis=1)
                        final_outcomes['SG_hard'] = final_positions.apply(lambda x: x.str.fullmatch("SG").sum(), axis=1)
                        final_outcomes['SF_hard'] = final_positions.apply(lambda x: x.str.fullmatch("SF").sum(), axis=1)
                        final_outcomes['PF_hard'] = final_positions.apply(lambda x: x.str.fullmatch("PF").sum(), axis=1)

                        final_outcomes['PG'] = 0
                        final_outcomes['SG'] = 0
                        final_outcomes['SF'] = 0
                        final_outcomes['PF'] = 0
                        final_outcomes['C'] = 0
                        final_outcomes['G'] = 0
                        final_outcomes['F'] = 0
                        final_outcomes['UTIL'] = 0

                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.1'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.2'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.1'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.3'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.2'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.4'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.3'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.5'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.4'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.6'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.5'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.7'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.6'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['C-count'] == 1) & (final_outcomes['pos.8'].str.contains("C")) & (final_outcomes['C'] == 0), final_outcomes['Player.7'], final_outcomes['C'])

                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.1'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.2'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.3'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.4'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.5'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.6'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PG_hard'] == 3) & (final_outcomes['Player.7'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['UTIL'])

                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player']) & (final_outcomes['UTIL'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.1'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.1']) & (final_outcomes['UTIL'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.2'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.2']) & (final_outcomes['UTIL'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.3'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.3']) & (final_outcomes['UTIL'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.4'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.4']) & (final_outcomes['UTIL'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.5'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.5']) & (final_outcomes['UTIL'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.6'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.6']) & (final_outcomes['UTIL'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['PG_hard'] >= 2) & (final_outcomes['Player.7'].map(pos_dict) == 'PG') & (final_outcomes['PG'] != final_outcomes['Player.7']) & (final_outcomes['UTIL'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['G'])

                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.1'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.2'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.3'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.4'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.5'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.6'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SG_hard'] == 3) & (final_outcomes['Player.7'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['UTIL'])

                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player']) & (final_outcomes['UTIL'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.1'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.1']) & (final_outcomes['UTIL'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.2'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.2']) & (final_outcomes['UTIL'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.3'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.3']) & (final_outcomes['UTIL'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.4'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.4']) & (final_outcomes['UTIL'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.5'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.5']) & (final_outcomes['UTIL'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.6'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.6']) & (final_outcomes['UTIL'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['SG_hard'] >= 2) & (final_outcomes['Player.7'].map(pos_dict) == 'SG') & (final_outcomes['SG'] != final_outcomes['Player.7']) & (final_outcomes['UTIL'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['G'])

                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.1'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.2'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.3'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.4'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.5'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.6'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['SF_hard'] == 3) & (final_outcomes['Player.7'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['UTIL'])

                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player']) & (final_outcomes['UTIL'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.1'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.1']) & (final_outcomes['UTIL'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.2'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.2']) & (final_outcomes['UTIL'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.3'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.3']) & (final_outcomes['UTIL'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.4'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.4']) & (final_outcomes['UTIL'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.5'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.5']) & (final_outcomes['UTIL'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.6'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.6']) & (final_outcomes['UTIL'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['SF_hard'] >= 2) & (final_outcomes['Player.7'].map(pos_dict) == 'SF') & (final_outcomes['SF'] != final_outcomes['Player.7']) & (final_outcomes['UTIL'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['F'])

                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.1'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.2'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.3'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.4'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.5'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.6'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['PF_hard'] == 3) & (final_outcomes['Player.7'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['UTIL'])

                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player']) & (final_outcomes['UTIL'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.1'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.1']) & (final_outcomes['UTIL'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.2'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.2']) & (final_outcomes['UTIL'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.3'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.3']) & (final_outcomes['UTIL'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.4'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.4']) & (final_outcomes['UTIL'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.5'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.5']) & (final_outcomes['UTIL'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.6'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.6']) & (final_outcomes['UTIL'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['PF_hard'] >= 2) & (final_outcomes['Player.7'].map(pos_dict) == 'PF') & (final_outcomes['PF'] != final_outcomes['Player.7']) & (final_outcomes['UTIL'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['F'])

                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.1'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.2'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.3'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.4'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.5'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.6'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['two_c'] == 2) & (final_outcomes['Player.7'].map(pos_dict) == 'C') & (final_outcomes['C'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['UTIL'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.1'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.1'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.1'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.1'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.1'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.1'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.1'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.1'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.1'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.2'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.2'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.2'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.2'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.2'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.2'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.2'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.2'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.2'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.3'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.3'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.3'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.3'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.3'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.3'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.3'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.3'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.3'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.4'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.4'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.4'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.4'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.4'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.4'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.4'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.4'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.4'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.5'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.5'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.5'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.5'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.5'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.5'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.5'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.5'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.5'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.6'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.6'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.6'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.6'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.6'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.6'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.6'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.6'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.6'], final_outcomes['C'])

                        final_outcomes['PG'] = np.where((final_outcomes['Player.7'].map(pos_dict) == 'PG') & (final_outcomes['PG'] == 0), final_outcomes['Player.7'], final_outcomes['PG'])
                        final_outcomes['SG'] = np.where((final_outcomes['Player.7'].map(pos_dict) == 'SG') & (final_outcomes['SG'] == 0), final_outcomes['Player.7'], final_outcomes['SG'])
                        final_outcomes['SF'] = np.where((final_outcomes['Player.7'].map(pos_dict) == 'SF') & (final_outcomes['SF'] == 0), final_outcomes['Player.7'], final_outcomes['SF'])
                        final_outcomes['PF'] = np.where((final_outcomes['Player.7'].map(pos_dict) == 'PF') & (final_outcomes['PF'] == 0), final_outcomes['Player.7'], final_outcomes['PF'])
                        final_outcomes['C'] = np.where((final_outcomes['Player.7'].map(pos_dict) == 'C') & (final_outcomes['C'] == 0), final_outcomes['Player.7'], final_outcomes['C'])

                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player'].map(pos_dict) == 'SF/PF'), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.1'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.2'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.3'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.4'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.5'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.6'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SG/SF'] == 1) & (final_outcomes['SF/PF'] == 1) & (final_outcomes['PF_hard'] >= 1) & (final_outcomes['Player.7'].map(pos_dict) == 'SF/PF'), final_outcomes['Player.7'], final_outcomes['SF'])

                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.1'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.2'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.1'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.3'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.2'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.4'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.3'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.5'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.4'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.6'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.5'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.7'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.6'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['PG-count'] == 1) & (final_outcomes['pos.8'].str.contains("PG")) & (final_outcomes['PG'] == 0), final_outcomes['Player.7'], final_outcomes['PG'])

                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.1'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.2'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.1'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.3'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.2'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.4'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.3'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.5'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.4'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.6'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.5'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.7'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.6'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['SG-count'] == 1) & (final_outcomes['pos.8'].str.contains("SG")) & (final_outcomes['SG'] == 0), final_outcomes['Player.7'], final_outcomes['SG'])

                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.1'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.2'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.3'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.4'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.5'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.6'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.7'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['SF-count'] == 1) & (final_outcomes['pos.8'].str.contains("SF")) & (final_outcomes['SF'] == 0), final_outcomes['Player.7'], final_outcomes['SF'])

                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.1'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.2'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.1'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.3'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.2'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.4'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.3'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.5'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.4'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.6'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.5'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.7'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.6'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['PF-count'] == 1) & (final_outcomes['pos.8'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player.7'], final_outcomes['PF'])


                        # #---------- AFTER CHECKING FOR SINGLE INSTANCE POSITIONS ----------#
                        final_outcomes['PG'] = np.where((final_outcomes['pos.1'].str.contains("PG")) & (final_outcomes['pos.1'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.2'].str.contains("PG")) & (final_outcomes['pos.2'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.1'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.3'].str.contains("PG")) & (final_outcomes['pos.3'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.2'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.4'].str.contains("PG")) & (final_outcomes['pos.4'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.3'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.5'].str.contains("PG")) & (final_outcomes['pos.5'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.4'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.6'].str.contains("PG")) & (final_outcomes['pos.6'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.5'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.7'].str.contains("PG")) & (final_outcomes['pos.7'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.6'], final_outcomes['PG'])
                        final_outcomes['PG'] = np.where((final_outcomes['pos.8'].str.contains("PG")) & (final_outcomes['pos.8'] == "PG/SG") & (final_outcomes['PG'] == 0), final_outcomes['Player.7'], final_outcomes['PG'])

                        final_outcomes['SG'] = np.where((final_outcomes['pos.1'].str.contains("SG")) & (final_outcomes['pos.1'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.2'].str.contains("SG")) & (final_outcomes['pos.2'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.3'].str.contains("SG")) & (final_outcomes['pos.3'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.4'].str.contains("SG")) & (final_outcomes['pos.4'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.5'].str.contains("SG")) & (final_outcomes['pos.5'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.6'].str.contains("SG")) & (final_outcomes['pos.6'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.7'].str.contains("SG")) & (final_outcomes['pos.7'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.8'].str.contains("SG")) & (final_outcomes['pos.8'] == "PG/SG") & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['SG'])

                        final_outcomes['SG'] = np.where((final_outcomes['pos.1'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.2'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.3'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.4'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.5'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.6'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.7'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['SG'])
                        final_outcomes['SG'] = np.where((final_outcomes['pos.8'].str.contains("SG")) & (final_outcomes['SG'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['SG'])

                        final_outcomes['SF'] = np.where((final_outcomes['pos.1'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.2'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.3'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.4'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.5'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.6'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.7'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.8'] == ("SG/SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['SF'])

                        final_outcomes['SF'] = np.where((final_outcomes['pos.1'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.2'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.3'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.4'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.5'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.6'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.7'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.8'] == ("SF/PF")) & (final_outcomes['PF_hard'] == 1) & (final_outcomes['SF'] == 0), final_outcomes['Player.7'], final_outcomes['SF'])

                        final_outcomes['SF'] = np.where((final_outcomes['pos.1'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.2'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.3'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.4'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.5'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.6'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.7'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.8'] == ("SF/PF")) & (final_outcomes['C-count'] == 4) & (final_outcomes['SF'] == 0), final_outcomes['Player.7'], final_outcomes['SF'])

                        final_outcomes['SF'] = np.where((final_outcomes['pos.1'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player']) & (final_outcomes['PG'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.2'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.1']) & (final_outcomes['PG'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.3'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.2']) & (final_outcomes['PG'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.4'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.3']) & (final_outcomes['PG'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.5'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.4']) & (final_outcomes['PG'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.6'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.5']) & (final_outcomes['PG'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.7'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.6']) & (final_outcomes['PG'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['SF'])
                        final_outcomes['SF'] = np.where((final_outcomes['pos.8'].str.contains("SF")) & (final_outcomes['SF'] == 0) & (final_outcomes['SG'] != final_outcomes['Player.7']) & (final_outcomes['PG'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['SF'])

                        final_outcomes['PF'] = np.where((final_outcomes['pos.1'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player']) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.2'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.1']) & (final_outcomes['C'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.3'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.2']) & (final_outcomes['C'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.4'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.3']) & (final_outcomes['C'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.5'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.4']) & (final_outcomes['C'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.6'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.5']) & (final_outcomes['C'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.7'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.6']) & (final_outcomes['C'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['PF'])
                        final_outcomes['PF'] = np.where((final_outcomes['pos.8'].str.contains("PF")) & (final_outcomes['PF'] == 0) & (final_outcomes['SF'] != final_outcomes['Player.7']) & (final_outcomes['C'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['PF'])

                        final_outcomes['C'] = np.where((final_outcomes['pos.1'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.2'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.3'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.4'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.5'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.6'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.7'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['C'])
                        final_outcomes['C'] = np.where((final_outcomes['pos.8'].str.contains("C")) & (final_outcomes['C'] == 0) & (final_outcomes['PF'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['C'])

                        #---------- AFTER UNIQUE POSITIONS ARE FILLED ----------#
                        final_outcomes['G'] = np.where((final_outcomes['pos.1'].str.contains("G")) & (~final_outcomes['pos.1'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player']) & (final_outcomes['SG'] != final_outcomes['Player']) & (final_outcomes['SF'] != final_outcomes['Player']) & (final_outcomes['PF'] != final_outcomes['Player']) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.2'].str.contains("G")) & (~final_outcomes['pos.2'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.1']) & (final_outcomes['SG'] != final_outcomes['Player.1']) & (final_outcomes['SF'] != final_outcomes['Player.1']) & (final_outcomes['PF'] != final_outcomes['Player.1']) & (final_outcomes['C'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.3'].str.contains("G")) & (~final_outcomes['pos.3'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.2']) & (final_outcomes['SG'] != final_outcomes['Player.2']) & (final_outcomes['SF'] != final_outcomes['Player.2']) & (final_outcomes['PF'] != final_outcomes['Player.2']) & (final_outcomes['C'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.4'].str.contains("G")) & (~final_outcomes['pos.4'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.3']) & (final_outcomes['SG'] != final_outcomes['Player.3']) & (final_outcomes['SF'] != final_outcomes['Player.3']) & (final_outcomes['PF'] != final_outcomes['Player.3']) & (final_outcomes['C'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.5'].str.contains("G")) & (~final_outcomes['pos.5'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.4']) & (final_outcomes['SG'] != final_outcomes['Player.4']) & (final_outcomes['SF'] != final_outcomes['Player.4']) & (final_outcomes['PF'] != final_outcomes['Player.4']) & (final_outcomes['C'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.6'].str.contains("G")) & (~final_outcomes['pos.6'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.5']) & (final_outcomes['SG'] != final_outcomes['Player.5']) & (final_outcomes['SF'] != final_outcomes['Player.5']) & (final_outcomes['PF'] != final_outcomes['Player.5']) & (final_outcomes['C'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.7'].str.contains("G")) & (~final_outcomes['pos.7'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.6']) & (final_outcomes['SG'] != final_outcomes['Player.6']) & (final_outcomes['SF'] != final_outcomes['Player.6']) & (final_outcomes['PF'] != final_outcomes['Player.6']) & (final_outcomes['C'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.8'].str.contains("G")) & (~final_outcomes['pos.8'].str.contains("F")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.7']) & (final_outcomes['SG'] != final_outcomes['Player.7']) & (final_outcomes['SF'] != final_outcomes['Player.7']) & (final_outcomes['PF'] != final_outcomes['Player.7']) & (final_outcomes['C'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['G'])

                        final_outcomes['G'] = np.where((final_outcomes['pos.1'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player']) & (final_outcomes['SG'] != final_outcomes['Player']) & (final_outcomes['SF'] != final_outcomes['Player']) & (final_outcomes['PF'] != final_outcomes['Player']) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.2'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.1']) & (final_outcomes['SG'] != final_outcomes['Player.1']) & (final_outcomes['SF'] != final_outcomes['Player.1']) & (final_outcomes['PF'] != final_outcomes['Player.1']) & (final_outcomes['C'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.3'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.2']) & (final_outcomes['SG'] != final_outcomes['Player.2']) & (final_outcomes['SF'] != final_outcomes['Player.2']) & (final_outcomes['PF'] != final_outcomes['Player.2']) & (final_outcomes['C'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.4'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.3']) & (final_outcomes['SG'] != final_outcomes['Player.3']) & (final_outcomes['SF'] != final_outcomes['Player.3']) & (final_outcomes['PF'] != final_outcomes['Player.3']) & (final_outcomes['C'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.5'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.4']) & (final_outcomes['SG'] != final_outcomes['Player.4']) & (final_outcomes['SF'] != final_outcomes['Player.4']) & (final_outcomes['PF'] != final_outcomes['Player.4']) & (final_outcomes['C'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.6'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.5']) & (final_outcomes['SG'] != final_outcomes['Player.5']) & (final_outcomes['SF'] != final_outcomes['Player.5']) & (final_outcomes['PF'] != final_outcomes['Player.5']) & (final_outcomes['C'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.7'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.6']) & (final_outcomes['SG'] != final_outcomes['Player.6']) & (final_outcomes['SF'] != final_outcomes['Player.6']) & (final_outcomes['PF'] != final_outcomes['Player.6']) & (final_outcomes['C'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['G'])
                        final_outcomes['G'] = np.where((final_outcomes['pos.8'].str.contains("G")) & (final_outcomes['G'] == 0) & (final_outcomes['PG'] != final_outcomes['Player.7']) & (final_outcomes['SG'] != final_outcomes['Player.7']) & (final_outcomes['SF'] != final_outcomes['Player.7']) & (final_outcomes['PF'] != final_outcomes['Player.7']) & (final_outcomes['C'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['G'])

                        final_outcomes['F'] = np.where((final_outcomes['pos.1'].str.contains("F")) & (~final_outcomes['pos.1'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player']) & (final_outcomes['PG'] != final_outcomes['Player']) & (final_outcomes['SG'] != final_outcomes['Player']) & (final_outcomes['SF'] != final_outcomes['Player']) & (final_outcomes['PF'] != final_outcomes['Player']) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.2'].str.contains("F")) & (~final_outcomes['pos.2'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.1']) & (final_outcomes['PG'] != final_outcomes['Player.1']) & (final_outcomes['SG'] != final_outcomes['Player.1']) & (final_outcomes['SF'] != final_outcomes['Player.1']) & (final_outcomes['PF'] != final_outcomes['Player.1']) & (final_outcomes['C'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.3'].str.contains("F")) & (~final_outcomes['pos.3'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.2']) & (final_outcomes['PG'] != final_outcomes['Player.2']) & (final_outcomes['SG'] != final_outcomes['Player.2']) & (final_outcomes['SF'] != final_outcomes['Player.2']) & (final_outcomes['PF'] != final_outcomes['Player.2']) & (final_outcomes['C'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.4'].str.contains("F")) & (~final_outcomes['pos.4'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.3']) & (final_outcomes['PG'] != final_outcomes['Player.3']) & (final_outcomes['SG'] != final_outcomes['Player.3']) & (final_outcomes['SF'] != final_outcomes['Player.3']) & (final_outcomes['PF'] != final_outcomes['Player.3']) & (final_outcomes['C'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.5'].str.contains("F")) & (~final_outcomes['pos.5'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.4']) & (final_outcomes['PG'] != final_outcomes['Player.4']) & (final_outcomes['SG'] != final_outcomes['Player.4']) & (final_outcomes['SF'] != final_outcomes['Player.4']) & (final_outcomes['PF'] != final_outcomes['Player.4']) & (final_outcomes['C'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.6'].str.contains("F")) & (~final_outcomes['pos.6'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.5']) & (final_outcomes['PG'] != final_outcomes['Player.5']) & (final_outcomes['SG'] != final_outcomes['Player.5']) & (final_outcomes['SF'] != final_outcomes['Player.5']) & (final_outcomes['PF'] != final_outcomes['Player.5']) & (final_outcomes['C'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.7'].str.contains("F")) & (~final_outcomes['pos.7'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.6']) & (final_outcomes['PG'] != final_outcomes['Player.6']) & (final_outcomes['SG'] != final_outcomes['Player.6']) & (final_outcomes['SF'] != final_outcomes['Player.6']) & (final_outcomes['PF'] != final_outcomes['Player.6']) & (final_outcomes['C'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.8'].str.contains("F")) & (~final_outcomes['pos.8'].str.contains("G")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.7']) & (final_outcomes['PG'] != final_outcomes['Player.7']) & (final_outcomes['SG'] != final_outcomes['Player.7']) & (final_outcomes['SF'] != final_outcomes['Player.7']) & (final_outcomes['PF'] != final_outcomes['Player.7']) & (final_outcomes['C'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['F'])

                        final_outcomes['F'] = np.where((final_outcomes['pos.1'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player']) & (final_outcomes['PG'] != final_outcomes['Player']) & (final_outcomes['SG'] != final_outcomes['Player']) & (final_outcomes['SF'] != final_outcomes['Player']) & (final_outcomes['PF'] != final_outcomes['Player']) & (final_outcomes['C'] != final_outcomes['Player']), final_outcomes['Player'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.2'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.1']) & (final_outcomes['PG'] != final_outcomes['Player.1']) & (final_outcomes['SG'] != final_outcomes['Player.1']) & (final_outcomes['SF'] != final_outcomes['Player.1']) & (final_outcomes['PF'] != final_outcomes['Player.1']) & (final_outcomes['C'] != final_outcomes['Player.1']), final_outcomes['Player.1'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.3'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.2']) & (final_outcomes['PG'] != final_outcomes['Player.2']) & (final_outcomes['SG'] != final_outcomes['Player.2']) & (final_outcomes['SF'] != final_outcomes['Player.2']) & (final_outcomes['PF'] != final_outcomes['Player.2']) & (final_outcomes['C'] != final_outcomes['Player.2']), final_outcomes['Player.2'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.4'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.3']) & (final_outcomes['PG'] != final_outcomes['Player.3']) & (final_outcomes['SG'] != final_outcomes['Player.3']) & (final_outcomes['SF'] != final_outcomes['Player.3']) & (final_outcomes['PF'] != final_outcomes['Player.3']) & (final_outcomes['C'] != final_outcomes['Player.3']), final_outcomes['Player.3'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.5'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.4']) & (final_outcomes['PG'] != final_outcomes['Player.4']) & (final_outcomes['SG'] != final_outcomes['Player.4']) & (final_outcomes['SF'] != final_outcomes['Player.4']) & (final_outcomes['PF'] != final_outcomes['Player.4']) & (final_outcomes['C'] != final_outcomes['Player.4']), final_outcomes['Player.4'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.6'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.5']) & (final_outcomes['PG'] != final_outcomes['Player.5']) & (final_outcomes['SG'] != final_outcomes['Player.5']) & (final_outcomes['SF'] != final_outcomes['Player.5']) & (final_outcomes['PF'] != final_outcomes['Player.5']) & (final_outcomes['C'] != final_outcomes['Player.5']), final_outcomes['Player.5'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.7'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.6']) & (final_outcomes['PG'] != final_outcomes['Player.6']) & (final_outcomes['SG'] != final_outcomes['Player.6']) & (final_outcomes['SF'] != final_outcomes['Player.6']) & (final_outcomes['PF'] != final_outcomes['Player.6']) & (final_outcomes['C'] != final_outcomes['Player.6']), final_outcomes['Player.6'], final_outcomes['F'])
                        final_outcomes['F'] = np.where((final_outcomes['pos.8'].str.contains("F")) & (final_outcomes['F'] == 0) & (final_outcomes['G'] != final_outcomes['Player.7']) & (final_outcomes['PG'] != final_outcomes['Player.7']) & (final_outcomes['SG'] != final_outcomes['Player.7']) & (final_outcomes['SF'] != final_outcomes['Player.7']) & (final_outcomes['PF'] != final_outcomes['Player.7']) & (final_outcomes['C'] != final_outcomes['Player.7']), final_outcomes['Player.7'], final_outcomes['F'])

                        # #---------- FILL UNIQUE ----------#
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0) 
                                                          & (final_outcomes['PG'] != final_outcomes['Player']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player'])
                                                          & (final_outcomes['C'] != final_outcomes['Player'])
                                                          & (final_outcomes['G'] != final_outcomes['Player'])
                                                          & (final_outcomes['F'] != final_outcomes['Player'])
                                                          , final_outcomes['Player'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.1']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.1'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.1'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.1'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.1'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.1'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.1'])
                                                          , final_outcomes['Player.1'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.2']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.2'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.2'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.2'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.2'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.2'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.2'])
                                                          , final_outcomes['Player.2'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.3']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.3'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.3'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.3'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.3'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.3'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.3'])
                                                          , final_outcomes['Player.3'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.4']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.4'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.4'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.4'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.4'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.4'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.4'])
                                                          , final_outcomes['Player.4'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.5']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.5'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.5'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.5'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.5'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.5'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.5'])
                                                          , final_outcomes['Player.5'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.6']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.6'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.6'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.6'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.6'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.6'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.6'])
                                                          , final_outcomes['Player.6'], final_outcomes['UTIL'])
                        final_outcomes['UTIL'] = np.where((final_outcomes['UTIL'] == 0)
                                                          & (final_outcomes['PG'] != final_outcomes['Player.7']) 
                                                          & (final_outcomes['SG'] != final_outcomes['Player.7'])
                                                          & (final_outcomes['SF'] != final_outcomes['Player.7'])
                                                          & (final_outcomes['PF'] != final_outcomes['Player.7'])
                                                          & (final_outcomes['C'] != final_outcomes['Player.7'])
                                                          & (final_outcomes['G'] != final_outcomes['Player.7'])
                                                          & (final_outcomes['F'] != final_outcomes['Player.7'])
                                                          , final_outcomes['Player.7'], final_outcomes['UTIL'])
                        final_outcomes = final_outcomes.loc[final_outcomes['two_c'] <= 2]
                        final_sorted_outcomes = final_outcomes[['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']]
                        final_sorted_outcomes.rename(columns={"PG": "Player", "SG": "Player.1", "SF": "Player.2", "PF": "Player.3", "C": "Player.4", "G": "Player.5", "F": "Player.6", "UTIL": "Player.7"}, inplace = True)
                        final_sorted_outcomes['Salary'] = sum([final_sorted_outcomes['Player'].map(player_sal),
                                final_sorted_outcomes['Player.1'].map(player_sal),
                                final_sorted_outcomes['Player.2'].map(player_sal),
                                final_sorted_outcomes['Player.3'].map(player_sal),
                                final_sorted_outcomes['Player.4'].map(player_sal),
                                final_sorted_outcomes['Player.5'].map(player_sal),
                                final_sorted_outcomes['Player.6'].map(player_sal),
                                final_sorted_outcomes['Player.7'].map(player_sal)])
                        final_sorted_outcomes['Proj'] = sum([final_sorted_outcomes['Player'].map(player_proj),
                                final_sorted_outcomes['Player.1'].map(player_proj),
                                final_sorted_outcomes['Player.2'].map(player_proj),
                                final_sorted_outcomes['Player.3'].map(player_proj),
                                final_sorted_outcomes['Player.4'].map(player_proj),
                                final_sorted_outcomes['Player.5'].map(player_proj),
                                final_sorted_outcomes['Player.6'].map(player_proj),
                                final_sorted_outcomes['Player.7'].map(player_proj)])
                        final_sorted_outcomes['Proj Own%'] = sum([final_sorted_outcomes['Player'].map(player_own),
                                final_sorted_outcomes['Player.1'].map(player_own),
                                final_sorted_outcomes['Player.2'].map(player_own),
                                final_sorted_outcomes['Player.3'].map(player_own),
                                final_sorted_outcomes['Player.4'].map(player_own),
                                final_sorted_outcomes['Player.5'].map(player_own),
                                final_sorted_outcomes['Player.6'].map(player_own),
                                final_sorted_outcomes['Player.7'].map(player_own)])
                        sort_df = final_sorted_outcomes.sort_values(by='Proj', ascending=False)
                        sort_df = sort_df.reset_index()
                        sort_df = sort_df.drop(['index'], axis=1)
                        display_frame = sort_df.apply(pd.to_numeric, errors='ignore')
                        display_frame = display_frame.drop_duplicates(subset=['Proj'])
                        display_frame = display_frame.round(2)
                
                        final_outcomes = display_frame
                        final_outcomes.rename(columns={'Player': 'Player_1', 'Player.1': 'Player_2', 'Player.2': 'Player_3', 'Player.3': 'Player_4', 'Player.4': 'Player_5', 'Player.5': 'Player_6', 'Player.6': 'Player_7', 'Player.7': 'Player_8'}, inplace = True)
                        final_outcomes['p1 id'] = final_outcomes['Player_1'].map(id_dict)
                        final_outcomes['p2 id'] = final_outcomes['Player_2'].map(id_dict)
                        final_outcomes['p3 id'] = final_outcomes['Player_3'].map(id_dict)
                        final_outcomes['p4 id'] = final_outcomes['Player_4'].map(id_dict)
                        final_outcomes['p5 id'] = final_outcomes['Player_5'].map(id_dict)
                        final_outcomes['p6 id'] = final_outcomes['Player_6'].map(id_dict)
                        final_outcomes['p7 id'] = final_outcomes['Player_7'].map(id_dict)
                        final_outcomes['p8 id'] = final_outcomes['Player_8'].map(id_dict)
                        final_outcomes = final_outcomes[['p1 id', 'p2 id', 'p3 id', 'p4 id', 'p5 id', 'p6 id', 'p7 id', 'p8 id']]
                        
                with col1:
                    st.download_button(
                        label="Export Lineups",
                        data=convert_df_to_csv(final_outcomes),
                        file_name='NBA_DFS_export.csv',
                        mime='text/csv',
                    )

                with hold_container:
                    hold_container = st.empty()
