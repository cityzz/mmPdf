import argparse
import os
import pandas as pd

'''
pip install pandas openpyxl
conda install pandas openpyxl
'''

def compare_with_double_check(file1_path, file2_path):
    # 自动生成输出文件名 (保留原有的扩展名)
    name1, ext1 = os.path.splitext(file1_path)
    name2, ext2 = os.path.splitext(file2_path)
    output1_path = f"{name1}_res{ext1}"
    output2_path = f"{name2}_res{ext2}"

    print(f"正在加载 Excel 文件...")
    print(f"表格 1: {file1_path}")
    print(f"表格 2: {file2_path}")

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
    df2["Combined_Normal"] = surname_clean + firstname_clean
    df2["Combined_Reverse"] = firstname_clean + surname_clean

    # 4. 生成表格1的对比集合
    set_client_1 = set(df1["Client_Clean"])

    # --- 开始比对表格 2 ---
    print("正在对表格2进行双重交叉比对...")
    df2["对比结果"] = df2["Combined_Normal"].apply(
        lambda x: "正常" if x in set_client_1 else "表格1缺失"
    )

    df2["二次确认结果"] = df2["对比结果"]
    missing_idx = df2[df2["对比结果"] == "表格1缺失"].index

    for idx in missing_idx:
        reverse_name = df2.loc[idx, "Combined_Reverse"]
        if reverse_name in set_client_1:
            df2.loc[idx, "二次确认结果"] = (
                "正常 (已通过 Firstname+Surname 确认)"
            )
        else:
            df2.loc[idx, "二次确认结果"] = "绝对缺失 (双向比对皆无)"

    # --- 开始比对表格 1 ---
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

    # 6. 严格限制表格1的输出列
    standard_cols_1 = ["Client", "Statement", "对比结果"]
    final_cols_1 = [col for col in standard_cols_1 if col in df1.columns]
    df1_final = df1[final_cols_1]

    print("正在保存处理后的文件...")
    df1_final.to_excel(output1_path, index=False)
    df2.to_excel(output2_path, index=False)

    print("-" * 40)
    print("对比完成！文件已成功保存为：")
    print(f" -> {output1_path}")
    print(f" -> {output2_path}")
    print("-" * 40)


# ==================== 命令行参数解析（已升级别名） ====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Excel 姓名跨表双向智能比对工具"
    )

    # 同时支持 --f1 和 --file1。代码内部通过 args.file1 来获取具体的值
    parser.add_argument(
        "--f1",
        "--file1",
        dest="file1",
        required=True,
        help="表格1的路径 (包含 Client 和 Statement 列)",
    )

    # 同时支持 --f2 和 --file2。代码内部通过 args.file2 来获取具体的值
    parser.add_argument(
        "--f2",
        "--file2",
        dest="file2",
        required=True,
        help="表格2的路径 (包含 Surname 和 First Name 列)",
    )

    args = parser.parse_args()

    # 运行主函数
    compare_with_double_check(args.file1, args.file2)
