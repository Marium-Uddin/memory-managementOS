from flask import Flask, render_template, jsonify, request
import random
import time
from collections import deque

app = Flask(__name__)

class MemoryManager:
    def __init__(self, memory_size=16):
        self.memory_size = memory_size
        self.memory = [None] * memory_size
        self.page_table = {}
        self.processes = {}
        self.process_counter = 1
        self.allocation_queue = deque()  # For FIFO
        self.stats = {'page_faults': 0, 'page_hits': 0}
        self.logs = []
        
    def add_log(self, message):
        self.logs.append({'timestamp': time.time(), 'message': message})
        if len(self.logs) > 50:
            self.logs.pop(0)
    
    def create_process(self):
        pid = self.process_counter
        size = random.randint(2, 4)
        color = f"hsl({(pid * 137) % 360}, 70%, 60%)"
        
        process = {
            'pid': pid,
            'size': size,
            'pages': [{'page_num': i, 'frame_num': None} for i in range(size)],
            'color': color
        }
        
        self.processes[pid] = process
        self.process_counter += 1
        self.add_log(f"Process P{pid} created ({size} pages)")
        
        return process
    
    def find_free_frame(self):
        for i, frame in enumerate(self.memory):
            if frame is None:
                return i
        return -1
    
    def find_victim_fifo(self):
        if self.allocation_queue:
            return self.allocation_queue[0]
        return -1
    
    def find_victim_lru(self):
        oldest_time = float('inf')
        victim_frame = -1
        
        for key, value in self.page_table.items():
            if value['last_used'] < oldest_time:
                oldest_time = value['last_used']
                victim_frame = value['frame_num']
        
        return victim_frame
    
    def allocate_page(self, pid, page_num, algorithm='fifo'):
        if pid not in self.processes:
            return {'success': False, 'error': 'Process not found'}
        
        key = f"P{pid}-{page_num}"
        
        # Check if already in memory (page hit)
        if key in self.page_table and self.page_table[key]['frame_num'] is not None:
            self.stats['page_hits'] += 1
            self.page_table[key]['last_used'] = time.time()
            self.add_log(f"Page hit: P{pid} page {page_num}")
            return {'success': True, 'hit': True}
        
        # Page fault
        self.stats['page_faults'] += 1
        frame_num = self.find_free_frame()
        
        # Need page replacement
        if frame_num == -1:
            if algorithm == 'fifo':
                frame_num = self.find_victim_fifo()
            else:  # LRU
                frame_num = self.find_victim_lru()
            
            if frame_num == -1:
                return {'success': False, 'error': 'No frames available'}
            
            # Find and evict victim
            victim_key = None
            for k, v in self.page_table.items():
                if v['frame_num'] == frame_num:
                    victim_key = k
                    break
            
            if victim_key:
                victim_parts = victim_key.split('-')
                victim_pid = int(victim_parts[0][1:])
                victim_page = int(victim_parts[1])
                self.add_log(f"Page fault: Evicting P{victim_pid} page {victim_page}")
                
                # Remove from queue if FIFO
                if algorithm == 'fifo':
                    self.allocation_queue.remove(frame_num)
                
                del self.page_table[victim_key]
        
        # Allocate new page
        process = self.processes[pid]
        self.memory[frame_num] = {
            'pid': pid,
            'page_num': page_num,
            'color': process['color']
        }
        
        current_time = time.time()
        self.page_table[key] = {
            'frame_num': frame_num,
            'alloc_time': current_time,
            'last_used': current_time
        }
        
        if algorithm == 'fifo':
            self.allocation_queue.append(frame_num)
        
        self.add_log(f"Allocated P{pid} page {page_num} to frame {frame_num}")
        return {'success': True, 'hit': False}
    
    def remove_process(self, pid):
        if pid not in self.processes:
            return {'success': False, 'error': 'Process not found'}
        
        # Free memory frames
        for i in range(len(self.memory)):
            if self.memory[i] and self.memory[i]['pid'] == pid:
                # Remove from FIFO queue
                if i in self.allocation_queue:
                    self.allocation_queue.remove(i)
                self.memory[i] = None
        
        # Remove from page table
        keys_to_remove = [k for k in self.page_table.keys() if k.startswith(f"P{pid}-")]
        for key in keys_to_remove:
            del self.page_table[key]
        
        # Remove process
        del self.processes[pid]
        self.add_log(f"Process P{pid} terminated")
        
        return {'success': True}
    
    def get_state(self):
        return {
            'memory': self.memory,
            'processes': list(self.processes.values()),
            'stats': self.stats,
            'logs': self.logs[-10:]  # Last 10 logs
        }
    
    def reset(self):
        self.__init__(self.memory_size)

# Global memory manager instance
memory_manager = MemoryManager()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify(memory_manager.get_state())

@app.route('/api/create_process', methods=['POST'])
def create_process():
    process = memory_manager.create_process()
    return jsonify({'success': True, 'process': process})

@app.route('/api/allocate_page', methods=['POST'])
def allocate_page():
    data = request.json
    pid = data.get('pid')
    page_num = data.get('page_num')
    algorithm = data.get('algorithm', 'fifo')
    
    result = memory_manager.allocate_page(pid, page_num, algorithm)
    return jsonify(result)

@app.route('/api/remove_process', methods=['POST'])
def remove_process():
    data = request.json
    pid = data.get('pid')
    
    result = memory_manager.remove_process(pid)
    return jsonify(result)

@app.route('/api/simulate_access', methods=['POST'])
def simulate_access():
    data = request.json
    algorithm = data.get('algorithm', 'fifo')
    
    if not memory_manager.processes:
        return jsonify({'success': False, 'error': 'No processes running'})
    
    # Random process and page
    pid = random.choice(list(memory_manager.processes.keys()))
    process = memory_manager.processes[pid]
    page_num = random.randint(0, process['size'] - 1)
    
    result = memory_manager.allocate_page(pid, page_num, algorithm)
    return jsonify(result)

@app.route('/api/reset', methods=['POST'])
def reset():
    memory_manager.reset()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)