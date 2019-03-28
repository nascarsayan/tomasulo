#%%
import json
from collections import defaultdict

NREGS = 8
clin = lambda : input().strip()

class InstrQ:
  def __init__(self):
    self.queue = []
  
  def push(self, inst):
    self.queue.append(inst)
  
  def pop(self):
    return self.queue.pop(0)

  def peek(self):
    return self.queue[0]
  
  def isEmpty(self):
    return not self.queue


class RF:
  def __init__(self, size=8):
    self.size = size
    self.reg = [None] * self.size
  
  def setr(self, idx, val):
    self.reg[idx] = val
  
  def getr(self, idx):
    return self.reg[idx]



class RAT:
  def __init__(self, rf, size=8):
    self.size = size
    self.reg = [None] * self.size
    self.rf = rf
  
  def setr(self, idx, val):
    self.reg[idx] = val
  
  def getr(self, idx):
    ref = self.reg[idx]
    if ref:
      return ('RAT', ref)
    return ('ABS', self.rf.getr(idx))

  def clear(self, bus):
    busdata = bus.getb()
    rspos = self.reg.index(busdata['rs'])
    if rspos:
      self.rf[rspos] = busdata['val']
      self.reg[rspos] = None


class Bus:
  def __init__(self):
    self.data = None
  
  def getb(self):
    return self.data

  def setb(self, data):
    self.data = data


class ALU:
  def __init__(self, functs):
    self.functs = functs
    self.reset()
    
  def reset(self):
    self.t = 0
    self.opcode = None
    self.res = None
    self.op1 = None
    self.op2 = None
  
  def incr(self):
    self.t += 1
  
  def execute(self, opcode, res, op1, op2):
    self.t = 0
    self.opcode = opcode
    self.res = res
    self.op1 = op1
    self.op2 = op2

  def outp(self):
    if self.t == self.functs[self.opcode].t:
      res = {
        'rs': self.res,
        'val': self.functs[self.opcode].funct(self.op1, self.op2)
      }
      return res
    return None
  

class ReserSt:
  def __init__(self, idx=None):
    fields = ['op', 'j', 'k', 'disp']
    self.content = {
      'idx': idx,
      'valid': False,
      'busy': False,
    }
    self.t = {
      'issue': None,
      'capture': None,
      'dispatch': None
    }
    for field in fields:
      self.content[field] = None
  
  def setr(self, instr, rat):
    [opcode, res, op1, op2] = instr
    self.content['valid'] = True
    self.content['busy'] = True
    self.content['op'] = opcode
    self.content['j'] = rat.getr[op1]
    self.content['k'] = rat.getr[op2]
    self.t['issue'] = currT
    rat.setr(res, self.content['idx'])

  def capture(self, busdata):
    if self.content['j'] == ('RAT', busdata['rs']):
      self.content['j'] = ('ABS', busdata['val'])
    if self.content['k'] == ('RAT', busdata['rs']):
      self.content['k'] = ('ABS', busdata['val'])
  
  def clear(self):
    self.valid = False

  def __str__(self):
    return json.dumps(self.content)
  
  def __repr__(self):
    return json.dumps(self.content)


class ReserALU:
  def __init__(self, tag, size, functs, st=0):
    self.tag = tag
    self.size = size
    self.RS = [ReserSt(st + i) for i in range(size)]
    self.alu = ALU(functs)
    self.valid = [0] * self.size
  
  def getr(self, idx):
    return self.RS[idx]

  def setr(self, instr, rat):
    emppos = self.valid.index(0)
    self.RS[emppos].setr(instr, rat)
    self.valid[emppos] = 1

  def isFull(self):
    return sum(self.valid) == self.size

  def capture(self, busdata):
    for RSi in self.RS:
      RSi.capture(busdata)
  
  def clear(self, idx):
    self.valid[idx] = 0
      
  def __str__(self):
    return json.dumps(map(lambda x: x.content, self.RS))
    

class ReserStGrp:
  def __init__(self, rat, A=3, M=2):
    self.RG = {
      'A': ReserALU('M', M, [
        { 0: { 'funct': (lambda x, y: x + y), 't': 2 }},
        { 1: { 'funct': (lambda x, y: x - y), 't': 2 }},
      ]),
      'M': ReserALU('M', M, [
        { 2: { 'funct': (lambda x, y: x * y), 't': 10 }},
        { 3: { 'funct': (lambda x, y: x / y), 't': 40 }},
      ], A)
    }
    self.types = ['A', 'M']
    self.rat = rat

  def getr(self, idx):
    if not idx:
      return
    if idx < self.RG['A'].size:
      return self.RG['A'].getr(idx)
    return self.RG['M'].getr(idx - self.RG['A'].size)
  
  def setr(self, instr):
    if instr[0] < self.RG['A'].size:
      self.RG['A'].setr(instr, self.rat)
    self.RG['M'].setr(instr, self.rat)
  
  def isFull(self, instr):
    if instr[0] < self.RG['A'].size:
      return self.RG['A'].isFull()
    return self.RG['M'].isFull()

  def capture(self, bus):
    busdata = bus.getb()
    if busdata:
      self.RG['A'].capture(busdata)
      self.RG['M'].capture(busdata)
      if busdata['rs'] < self.RG['A'].size:
        self.RG['A'].clear(busdata['rs'])
      else:
        self.RG['M'].clear(busdata['rs'] - self.RG['A'].size)

  def __str__(self):
    RG = {}
    for t in self.types:
      RG[t] = list(map(lambda x: x.content, self.RG[t].RS))
    return json.dumps(RG)


#%%
iq = InstrQ()
rf = RF()
rat = RAT(rf)
bus = Bus()
rsg = ReserStGrp(rat)

nins = int(clin())
T = int(clin())
for i in range(nins):
  iq.push(list(map(lambda x: int(x), clin().split())))
for i in range(NREGS):
  rf.setr(i, int(clin()))

for currT in range(T):
  # issue
  instr = iq.peek()
  if not rsg.isFull(instr):
    rsg.setr(instr)
    iq.pop()
  
  # capture
  rsg.capture(bus)
  rat.clear(bus)

  # dispatch

