import re

filepath = 'templates/reportes.html'
with open(filepath, 'r') as f:
    content = f.read()

# Apply Dark Neon Theme
content = content.replace('background: #f8fafc', 'background: #09090b')
content = content.replace('color: #1e293b', 'color: #f8fafc')
content = content.replace('background: #ffffff', 'background: #18181b')
content = content.replace('border: 1px solid #e2e8f0', 'border: 1px solid #27272a')
content = content.replace('color:#64748b', 'color:#a1a1aa')
content = content.replace('color: #475569', 'color: #e4e4e7')
content = content.replace('background: #f1f5f9', 'background: #27272a')

# Topbar
content = content.replace('background:linear-gradient(135deg,#1e1a2e,#0d0b1f)', 'background:linear-gradient(135deg, #09090b, #18181b)')
content = content.replace('border-bottom:1px solid #312e5a', 'border-bottom:1px solid #27272a')

# Chart default colors
content = content.replace("Chart.defaults.color = '#64748b'", "Chart.defaults.color = '#a1a1aa'")
content = content.replace("Chart.defaults.borderColor = '#1e2838'", "Chart.defaults.borderColor = '#27272a'")

# Log Borders
content = content.replace('border-bottom:1px solid #1e2838', 'border-bottom:1px solid #27272a')

# Nodes Grid
content = content.replace("borderColor: ['#7c3aed','#2563eb','#059669']", "borderColor: ['#c084fc','#38bdf8','#4ade80']")
content = content.replace("backgroundColor: ['rgba(124,58,237,.7)','rgba(37,99,235,.7)','rgba(5,150,105,.7)']", "backgroundColor: ['rgba(192,132,252,.7)','rgba(56,189,248,.7)','rgba(74,222,128,.7)']")

# Hover effects
content = content.replace('box-shadow:0 8px 20px rgba(37,99,235,.4)', 'box-shadow:0 8px 20px rgba(56,189,248,.4)')

# Make it full width
content = content.replace('max-width:1200px', 'max-width:1600px')

# Adding glowing borders to KPI
content = content.replace('.kpi:hover{transform:translateY(-3px)}', '.kpi:hover{transform:translateY(-3px); box-shadow: 0 0 15px rgba(255,255,255,0.1)}')
content = content.replace('.kpi.purple::before{background:linear-gradient(90deg,#7c3aed,#a78bfa)}', '.kpi.purple::before{background:linear-gradient(90deg,#c084fc,#e879f9); box-shadow: 0 0 10px #c084fc;}')
content = content.replace('.kpi.blue::before{background:linear-gradient(90deg,#2563eb,#60a5fa)}', '.kpi.blue::before{background:linear-gradient(90deg,#38bdf8,#7dd3fc); box-shadow: 0 0 10px #38bdf8;}')
content = content.replace('.kpi.green::before{background:linear-gradient(90deg,#059669,#2dd4bf)}', '.kpi.green::before{background:linear-gradient(90deg,#4ade80,#a7f3d0); box-shadow: 0 0 10px #4ade80;}')
content = content.replace('.kpi.orange::before{background:linear-gradient(90deg,#d97706,#fbbf24)}', '.kpi.orange::before{background:linear-gradient(90deg,#facc15,#fef08a); box-shadow: 0 0 10px #facc15;}')

with open(filepath, 'w') as f:
    f.write(content)

print("Dark theme applied to reportes.html")
