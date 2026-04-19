import json
import math

with open('advanced_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the candles data
start_idx = content.find('const data = [') + 13
end_idx = content.find('];\n', start_idx) + 1
if start_idx > 13 and end_idx > 1:
    data_str = content[start_idx:end_idx]
    try:
        data = json.loads(data_str)
        print(f"Total candles: {len(data)}")
        has_nan = False
        for c in data:
            if math.isnan(c['open']) or math.isnan(c['high']) or math.isnan(c['low']) or math.isnan(c['close']):
                print(f"NaN found at time {c['time']}")
                has_nan = True
                break
        if not has_nan:
            print("No NaNs found.")
            
        # Check sorting and duplicates
        prev_time = -1
        for i, c in enumerate(data):
            if c['time'] <= prev_time:
                print(f"Duplicate or unsorted time found at index {i}: {c['time']} <= {prev_time}")
                break
            prev_time = c['time']
    except Exception as e:
        print(f"Failed to parse data JSON: {e}")

# Extract markers
start_idx = content.find('const markers = [') + 16
end_idx = content.find('];\n', start_idx) + 1
if start_idx > 16 and end_idx > 1:
    markers_str = content[start_idx:end_idx]
    try:
        markers = json.loads(markers_str)
        print(f"Total markers: {len(markers)}")
        
        # Check sorting
        prev_time = -1
        for i, m in enumerate(markers):
            if m['time'] < prev_time:
                print(f"Unsorted marker at index {i}: {m['time']} < {prev_time}")
            prev_time = m['time']
    except Exception as e:
        print(f"Failed to parse markers JSON: {e}")
