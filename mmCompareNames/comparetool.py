## pip install pandas openpyxl

import pandas as pd


def compare_and_mark_excel_final(
    file1_path, file2_path, output1_path, output2_path
):
    print("正在加载 Excel 文件...")
    # 读取文件
    df1 = pd.read_excel(file1_path)
    df2 = pd.read_excel(file2_path)

    # 【新增保护步骤】检查并清理表格1可能存在的重复/幽灵列
    # 如果有类似 Statement.1, Statement.2 的列，且它们是空的或者不需要的，我们只保留前两列
    # 或者直接通过名字筛选出最初需要的列
    available_cols_1 = df1.columns.tolist()
    print(f"表格1原始列名: {available_cols_1}")

    print("正在进行深度归一化（去全部空格并转换为大写）...")

    # 1. 对表格1的 Client 列做深度清洗
    df1["Client_Clean"] = (
        df1["Client"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    )

    # 2. 对表格2的 Surname 和 First Name 进行深度清洗
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

    # 3. 拼接表格2的姓名
    df2["Combined_Clean"] = surname_clean + firstname_clean

    # 4. 生成用于比对的唯一集合
    set_client_1 = set(df1["Client_Clean"])
    set_combined_2 = set(df2["Combined_Clean"])

    print("正在进行交叉比对...")

    # 5. 对比表格 1 并添加结果列
    df1["对比结果"] = df1["Client_Clean"].apply(
        lambda x: "正常" if x in set_combined_2 else "表格2缺失"
    )

    # 6. 对比表格 2 并添加结果列
    df2["对比结果"] = df2["Combined_Clean"].apply(
        lambda x: "正常" if x in set_client_1 else "表格1缺失"
    )

    # 7. 移除用于后台比对的临时辅助列
    df1 = df1.drop(columns=["Client_Clean"])
    df2 = df2.drop(columns=["Combined_Clean"])

    # 【核心修复】严格限制表格1的输出列，强行丢弃任何多出来的 Statement.1
    # 我们只拿标准的 'Client', 'Statement', '对比结果' 这三列
    # 如果你的表格1原本还有其他列，可以在列表中继续添加
    standard_cols_1 = ["Client", "Statement", "对比结果"]
    # 确保这些列确实在 df1 中才进行筛选（防止因为拼写大小写报错）
    final_cols_1 = [col for col in standard_cols_1 if col in df1.columns]
    df1_final = df1[final_cols_1]

    print("正在保存处理后的文件...")
    # 保存严格过滤后的表格1
    df1_final.to_excel(output1_path, index=False)
    # 表格2保持原样输出
    df2.to_excel(output2_path, index=False)

    print("对比完成！")



# ==================== 参数配置与执行 ====================
if __name__ == "__main__":
    # 请在此处替换为你的实际文件名和路径
    FILE_1 = "Statement_ID_List.xlsx"  # 包含 Client, Statement
    FILE_2 = "TP_Client_names.xlsx"  # 包含 Surname, First Name 等

    # 输出结果的文件名
    OUTPUT_1 = "Statement_ID_List_res.xlsx"
    OUTPUT_2 = "TP_Client_names_res.xlsx"

    # 执行对比函数
    compare_and_mark_excel_final(FILE_1, FILE_2, OUTPUT_1, OUTPUT_2)
