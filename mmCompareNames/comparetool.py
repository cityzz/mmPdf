## pip install pandas openpyxl

import pandas as pd


def compare_and_mark_excel_perfect(
    file1_path, file2_path, output1_path, output2_path
):
    print("正在加载 Excel 文件...")
    df1 = pd.read_excel(file1_path)
    df2 = pd.read_excel(file2_path)

    print("正在进行深度归一化（去全部空格并转换为大写）...")

    # 1. 对表格1的 Client 列：转字符串 -> 转大写 -> 去除“所有”空格（包括中间的空格）
    # 使用 .str.replace(r'\s+', '', regex=True) 可以清除包括空格、Tab等在内的所有空白符
    df1["Client_Clean"] = (
        df1["Client"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    )

    # 2. 对表格2的 Surname 和 First Name 进行同样的处理
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

    # 3. 拼接表格2的姓名（此时两边都绝对没有空格了）
    df2["Combined_Clean"] = surname_clean + firstname_clean

    # 4. 生成用于比对的唯一集合
    set_client_1 = set(df1["Client_Clean"])
    set_combined_2 = set(df2["Combined_Clean"])

    print("正在进行交叉比对...")

    # 5. 对比表格 1
    df1["对比结果"] = df1["Client_Clean"].apply(
        lambda x: "正常" if x in set_combined_2 else "表格2缺失"
    )

    # 6. 对比表格 2
    df2["对比结果"] = df2["Combined_Clean"].apply(
        lambda x: "正常" if x in set_client_1 else "表格1缺失"
    )

    # 7. 移除辅助列，保持原表数据纯净（原表里的空格和大小写不会被修改）
    df1 = df1.drop(columns=["Client_Clean"])
    df2 = df2.drop(columns=["Combined_Clean"])

    print("正在保存处理后的文件...")
    df1.to_excel(output1_path, index=False)
    df2.to_excel(output2_path, index=False)

    print("对比完成")



# ==================== 参数配置与执行 ====================
if __name__ == "__main__":
    # 请在此处替换为你的实际文件名和路径
    FILE_1 = "Statement_ID_List.xlsx"  # 包含 Client, Statement
    FILE_2 = "TP_Client_names.xlsx"  # 包含 Surname, First Name 等

    # 输出结果的文件名
    OUTPUT_1 = "Statement_ID_List_res.xlsx"
    OUTPUT_2 = "TP_Client_names_res.xlsx"

    # 执行对比函数
    compare_and_mark_excel_perfect(FILE_1, FILE_2, OUTPUT_1, OUTPUT_2)
