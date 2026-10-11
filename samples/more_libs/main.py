import cowsay
from art import text2art
from tabulate import tabulate

print("--> [Python] Verifying dynamically installed libraries...")

# Use cowsay
cowsay_msg = cowsay.get_output_string("cow", "Dynamic dependencies installed & executed!")
print(cowsay_msg)

# Use art
ascii_banner = text2art("SUCCESS", font="small")
print(ascii_banner)

# Use tabulate
table_data = [
    ["cowsay", "6.1", "Dynamic pip install", "LOADED"],
    ["art", "6.4", "Dynamic pip install", "LOADED"],
    ["tabulate", "0.9.0", "Dynamic pip install", "LOADED"],
]
table_str = tabulate(table_data, headers=["Library", "Version", "Source", "Status"], tablefmt="grid")
print(table_str)

# Save output artifacts
with open("execution_report.txt", "w") as f:
    f.write("DYNAMIC DEPENDENCY EXECUTION REPORT\n")
    f.write("====================================\n\n")
    f.write(cowsay_msg + "\n\n")
    f.write(ascii_banner + "\n\n")
    f.write(table_str + "\n")

print("--> [Python] Successfully generated execution_report.txt!")
