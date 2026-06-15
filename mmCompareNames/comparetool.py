## pip install pandas openpyxl

import pandas as pd


def compare_with_double_check(
    file1_path, file2_path, output1_path, output2_path
):
    print("正在加载 Excel 文件...")
    df1 = pd.read_excel(file1_path)
    df2 = pd.read_excel(file2_path)

    print("正在进行深度归一化（去全部空格并转换为大写）...")

    # 1. 表格1 Client 列深度清洗
    df1["Client_Clean"] = (
        df1["Client"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    )

    # 2. 表格2 Surname 和 First Name 深度清洗
    surname_clean = (
        df2["Surname"]
        .astype(str)
        .str.upper()
        .str.replace(r"\s+", "", regex=True)
    )
    firstname_clean = (
        df2["First Name"]
        .astype(str)
        .str.upper()
        .str.replace(r"\s+", "", regex=True)
    )

    # 3. 准备两种拼接方式
    # 方式 A: Surname + First Name (正常顺序)
    df2["Combined_Normal"] = surname_clean + firstname_clean
    # 方式 B: First Name + Surname (反向顺序)
    df2["Combined_Reverse"] = firstname_clean + surname_clean

    # 4. 生成表格1的对比集合
    set_client_1 = set(df1["Client_Clean"])

    # --- 开始比对表格 2 ---
    print("正在对表格2进行双重交叉比对...")

    # 第一轮：正常顺序比对
    df2["对比结果"] = df2["Combined_Normal"].apply(
        lambda x: "正常" if x in set_client_1 else "表格1缺失"
    )

    # 第二轮：专门针对第一轮“缺失”的行，用反向顺序再次确定
    # 初始化“二次确认结果”列，默认和第一轮一致
    df2["二次确认结果"] = df2["对比结果"]

    # 找出第一轮缺失的行的索引
    missing_idx = df2[df2["对比结果"] == "表格1缺失"].index

    # 遍历这些缺失的行，用反向拼接去表格1里找
    for idx in missing_idx:
        reverse_name = df2.loc[idx, "Combined_Reverse"]
        if reverse_name in set_client_1:
            # 如果反向找到了，标记为已确认，并注明是顺序颠倒
            df2.loc[idx, "二次确认结果"] = (
                "正常 (已通过 Firstname+Surname 确认)"
            )
        else:
            df2.loc[idx, "二次确认结果"] = "绝对缺失 (双向比对皆无)"

    # --- 开始比对表格 1 ---
    # 表格1需要同时看表格2的“正向”和“反向”集合
    set_combined_normal = set(df2["Combined_Normal"])
    set_combined_reverse = set(df2["Combined_Reverse"])

    df1["对比结果"] = df1["Client_Clean"].apply(
        lambda x: (
            "正常"
            if (x in set_combined_normal or x in set_combined_reverse)
            else "表格2缺失"
        )
    )

    # 5. 清理辅助列
    df1 = df1.drop(columns=["Client_Clean"])
    df2 = df2.drop(columns=["Combined_Normal", "Combined_Reverse"])

    # 6. 严格限制表格1的输出列（防止多出 Statement.1）
    standard_cols_1 = ["Client", "Statement", "对比结果"]
    final_cols_1 = [col for col in standard_cols_1 if col in df1.columns]
    df1_final = df1[final_cols_1]

    print("正在保存处理后的文件...")
    df1_final.to_excel(output1_path, index=False)
    df2.to_excel(output2_path, index=False)

    print("双重对比完成！已成功保存结果。")



# ==================== 参数配置与执行 ====================
if __name__ == "__main__":
    # 请在此处替换为你的实际文件名和路径
    FILE_1 = "Statement_ID_List.xlsx"  # 包含 Client, Statement
    FILE_2 = "TP_Client_names.xlsx"  # 包含 Surname, First Name 等

    # 输出结果的文件名
    OUTPUT_1 = "Statement_ID_List_res.xlsx"
    OUTPUT_2 = "TP_Client_names_res.xlsx"

    # 执行对比函数
    compare_with_double_check(FILE_1, FILE_2, OUTPUT_1, OUTPUT_2)
