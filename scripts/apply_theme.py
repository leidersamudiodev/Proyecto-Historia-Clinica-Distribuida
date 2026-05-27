import glob
import re

files = glob.glob('templates/*.html') + ['static/style.css']

# The user wants "blanco con verde menta-azulado"
# Menta-azulado (Teal/Mint): #14b8a6, #0d9488, #0f766e
# Blanco: #ffffff, #f8fafc, #f1f5f9

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Gradients
    content = re.sub(r'linear-gradient\(135deg,\s*#667eea\s*0%,\s*#764ba2\s*100%\)', 'linear-gradient(135deg, #14b8a6 0%, #0284c7 100%)', content)
    content = re.sub(r'linear-gradient\(to right,\s*#4f46e5,\s*#7c3aed\)', 'linear-gradient(to right, #0d9488, #0284c7)', content)
    content = re.sub(r'linear-gradient\(to right,\s*#3730a3,\s*#5b21b6\)', 'linear-gradient(to right, #0f766e, #0369a1)', content)
    
    # Specific Purples/Blues -> Mint/Sky Blue
    content = content.replace('#667eea', '#14b8a6')
    content = content.replace('#764ba2', '#0284c7')
    content = content.replace('#4f46e5', '#0d9488')
    content = content.replace('#4338ca', '#0f766e')
    content = content.replace('#3730a3', '#115e59')
    content = content.replace('#818cf8', '#5eead4')
    content = content.replace('#e0e7ff', '#ccfbf1') # Indigo 100 -> Teal 100
    content = content.replace('#c7d2fe', '#99f6e4') # Indigo 200 -> Teal 200

    # Dark Theme Backgrounds -> Light Theme Backgrounds
    content = content.replace('bg-gray-900', 'bg-slate-50')
    content = content.replace('bg-gray-800', 'bg-white')
    content = content.replace('text-white', 'text-slate-800')
    # Let's not blindly replace text-white because it's used on buttons too.
    
    # Actually, the user's templates are a mix of vanilla CSS and tailwind classes.
    # We will just replace the core colors.
    
    # In style.css (Dashboard)
    if 'style.css' in filepath:
        content = content.replace('--bg-color: #0d1117', '--bg-color: #f0fdfa') # teal-50
        content = content.replace('--card-bg: rgba(22, 27, 34, 0.7)', '--card-bg: rgba(255, 255, 255, 0.9)')
        content = content.replace('--text-primary: #f0f6fc', '--text-primary: #0f172a')
        content = content.replace('--text-secondary: #8b949e', '--text-secondary: #475569')
        content = content.replace('--border-color: #30363d', '--border-color: #cbd5e1')
        content = content.replace('--accent-color: #58a6ff', '--accent-color: #0d9488')
        content = content.replace('rgba(88, 166, 255, 0.1)', 'rgba(13, 148, 136, 0.1)')
        content = content.replace('rgba(35, 134, 54, 0.1)', 'rgba(2, 132, 199, 0.1)')
        content = content.replace('background: #0d1117', 'background: #ffffff')
    
    with open(filepath, 'w') as f:
        f.write(content)

for f in files:
    process_file(f)
print("Theme applied successfully.")
