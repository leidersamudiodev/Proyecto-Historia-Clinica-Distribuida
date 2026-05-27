import glob
import re

files = glob.glob('templates/*.html')

color_map = {
    '#0f1117': '#f8fafc',
    '#1a1f2e': '#ffffff',
    '#1e293b': '#f1f5f9',
    '#0d1117': '#f4f7f6',
    '#1a2e1f': '#e6fdf2',
    '#0d1f11': '#ffffff',
    
    '#e2e8f0': '#1e293b',
    '#94a3b8': '#475569',
    '#fff': '#ffffff', 
    '#ffffff': '#ffffff', # Keep white buttons white
    
    '#2d3748': '#e2e8f0',
    '#1e2d1f': '#dcfce7',
    '#2d4a35': '#dcfce7',
    
    # Update green/mint colors to mint-blue
    '#4ade80': '#0d9488',
    '#22c55e': '#14b8a6',
    '#15803d': '#0f766e',
    '#166534': '#115e59',
    '#34d399': '#2dd4bf',
    
    # Gradients
    '#667eea': '#14b8a6',
    '#764ba2': '#0369a1',
    '#6b7280': '#cbd5e1'
}

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # We don't want to replace #fff in button text color. 
    # Let's be careful.
    
    # Replace body and container backgrounds specifically
    content = re.sub(r'background:\s*#0f1117', 'background: #f8fafc', content)
    content = re.sub(r'background:\s*#1a1f2e', 'background: #ffffff', content)
    content = re.sub(r'background-color:\s*#0f1117', 'background-color: #f8fafc', content)
    
    # Text colors
    content = re.sub(r'color:\s*#e2e8f0', 'color: #1e293b', content)
    content = re.sub(r'color:\s*#94a3b8', 'color: #475569', content)
    
    # Borders
    content = re.sub(r'border:\s*1px solid #2d3748', 'border: 1px solid #e2e8f0', content)
    content = re.sub(r'border-bottom:\s*1px solid #2d4a35', 'border-bottom: 1px solid #dcfce7', content)
    content = re.sub(r'border-color:\s*#2d3748', 'border-color: #e2e8f0', content)
    
    # Inputs
    content = re.sub(r'input,select,textarea\{background:\s*#0f1117', 'input,select,textarea{background: #ffffff', content)
    
    # Accents
    content = content.replace('#4ade80', '#0d9488')
    content = content.replace('#22c55e', '#14b8a6')
    content = content.replace('#15803d', '#0f766e')
    content = content.replace('#166534', '#115e59')
    content = content.replace('#34d399', '#2dd4bf')
    
    # Ensure button text is still white if primary
    content = re.sub(r'color:\s*#fff', 'color: #ffffff', content)
    
    # Gradients
    content = re.sub(r'linear-gradient\(135deg,\s*#1a2e1f,\s*#0d1f11\)', 'linear-gradient(135deg, #ccfbf1, #ffffff)', content)
    
    # Replace background:#1e293b for secondary buttons
    content = re.sub(r'background:\s*#1e293b', 'background: #f1f5f9', content)
    
    with open(filepath, 'w') as f:
        f.write(content)

for f in files:
    process_file(f)
print("Light theme applied.")
