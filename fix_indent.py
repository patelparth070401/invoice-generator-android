with open('invoice_app/flet_ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
for i, line in enumerate(lines):
    if 29 <= i <= 245: # 0-indexed, so lines 30 to 246
        if line.strip() == '':
            out.append(line)
        else:
            out.append('    ' + line)
    else:
        out.append(line)

with open('invoice_app/flet_ui.py', 'w', encoding='utf-8') as f:
    f.writelines(out)
