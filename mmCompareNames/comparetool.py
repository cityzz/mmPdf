import pandas as pd
import argparse
import os


'''
pip install pandas openpyxl
conda install pandas openpyxl
'''


def compare_with_strict_double_check(file1_path, file2_path):
    name1, ext1 = os.path.splitext(file1_path)
    name2, ext2 = os.path.splitext(file2_path)
    output1_path = f"{name1}_res{ext1}"
    output2_path = f"{name2}_res{ext2}"

    print("正在加载 Excel 文件...")
    df1 = pd.read_excel(file1_path)
    df2 = pd.read_excel(file2_path)

    print("正在进行深度归一化...")
    # 表格1清洗
    df1['Client_Clean'] = df1['Client'].astype(str).str.upper().str.replace(r'\s+', '', regex=True)

    # 表格2清洗
    surname_clean = df2['Surname'].astype(str).str.upper().str.replace(r'\s+', '', regex=True)
    firstname_clean = df2['First Name'].astype(str).str.upper().str.replace(r'\s+', '', regex=True)

    df2['Combined_Normal'] = surname_clean + firstname_clean   # 正向: Surname + First Name
    df2['Combined_Reverse'] = firstname_clean + surname_clean  # 反向: First Name + Surname

    # 建立表格1的剩余未匹配集合（动态核销库）
    remaining_clients_1 = set(df1['Client_Clean'])

    # 记录表格2每一行的最终匹配到的表格1的Client值（用于反向同步给表格1）
    # 如果匹配成功，这里会存入它在表格1里实际对应的那个Clean名字
    df2['Matched_In_T1'] = None

    print("--- 开启严格双轮动态核销比对 ---")

    # 【第一轮：正向匹配】
    # 优先让所有正向拼写正确的行进行匹配
    for idx, row in df2.iterrows():
        normal_name = row['Combined_Normal']
        if normal_name in remaining_clients_1:
            df2.loc[idx, 'Matched_In_T1'] = normal_name
            df2.loc[idx, '对比结果'] = '正常'
            df2.loc[idx, '二次确认结果'] = '正常'
            # 已经匹配过了，从核销库中移除，防止表格2的其他行重复认领
            remaining_clients_1.remove(normal_name)

    # 【第二轮：反向确认】
    # 针对第一轮没有匹配成功的行，尝试用反向拼写去匹配【剩下的】表格1数据
    for idx, row in df2.iterrows():
        if pd.isna(df2.loc[idx, 'Matched_In_T1']): # 如果第一轮没配上
            reverse_name = row['Combined_Reverse']
            if reverse_name in remaining_clients_1:
                df2.loc[idx, 'Matched_In_T1'] = reverse_name
                df2.loc[idx, '对比结果'] = '表格1缺失'
                df2.loc[idx, '二次确认结果'] = '正常 (已通过 Firstname+Surname 确认)'
                remaining_clients_1.remove(reverse_name) # 核销
            else:
                df2.loc[idx, '对比结果'] = '表格1缺失'
                df2.loc[idx, '二次确认结果'] = '绝对缺失 (双向比对皆无)'

    print("--- 正在根据核销结果同步表格1 ---")
    # 表格2所有成功匹配到表格1的Clean名字集合
    all_matched_by_t2 = set(df2['Matched_In_T1'].dropna())

    # 表格1的某一行只要它的 Clean 名字在表格2的匹配成功库里，就是正常，否则就是表格2缺失
    df1['对比结果'] = df1['Client_Clean'].apply(
        lambda x: '正常' if x in all_matched_by_t2 else '表格2缺失'
    )

    # 5. 清理辅助列
    df1 = df1.drop(columns=['Client_Clean'])
    df2 = df2.drop(columns=['Combined_Normal', 'Combined_Reverse', 'Matched_In_T1'])

    # 6. 严格限制表格1的输出列
    standard_cols_1 = ['Client', 'Statement', '对比结果']
    final_cols_1 = [col for col in standard_cols_1 if col in df1.columns]
    df1_final = df1[final_cols_1]

    print("正在保存处理后的文件...")
    df1_final.to_excel(output1_path, index=False)
    df2.to_excel(output2_path, index=False)

    print("-" * 40)
    print("严格对比完成！文件已保存：")
    print(f" -> {output1_path}")
    print(f" -> {output2_path}")
    print("-" * 40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Excel 姓名跨表双向严格核销比对工具")
    parser.add_argument("--f1", "--file1", dest="file1", required=True, help="表格1路径")
    parser.add_argument("--f2", "--file2", dest="file2", required=True, help="表格2路径")
    args = parser.parse_args()

    compare_with_strict_double_check(args.file1, args.file2)
