#%%
import json
from collections import defaultdict
from tabulate import tabulate

NREGS = 8
clin = lambda: input().strip()
remNone = lambda x: map(lambda y: '' if y is None or False else y, x)

class InstrQ:

  def __init__(self):
    self.queue = []
    self.funcmap = {0: 'ADD', 1: 'SUB', 2: 'MUL', 3: 'DIV'}

  def push(self, inst):
    self.queue.append(inst)

  def pop(self):
    return self.queue.pop(0)

  def peek(self):
    return self.queue[0]

  def isEmpty(self):
    return not self.queue
  
  def __repr__(self):
    headers = ['OPCODE', 'DST OP', 'SRC OP1', 'SRC OP2']
    table = []
    for instr in self.queue:
      row = [self.funcmap[instr[0]]]
      row.extend(['RS%d' %i for i in instr[1:]])
      table.append(row)
    return tabulate(table, headers, tablefmt='fancy_grid')


class RF:

  def __init__(self, size=8):
    self.size = size
    self.regFile = [None] * self.size

  def setr(self, idx, val):
    self.regFile[idx] = val

  def getr(self, idx):
    return self.regFile[idx]


class RAT:

  def __init__(self, rf, size=8):
    self.size = size
    self.regFile = [None] * self.size
    self.rf = rf

  def setr(self, idx, val):
    self.regFile[idx] = val

  def getr(self, idx):
    ref = self.regFile[idx]
    if ref:
      return ('RAT', ref)
    return ('ABS', self.rf.getr(idx))

  def clear(self, bus):
    busdata = bus.getb()
    if busdata is None:
      return
    rspos = self.regFile.index(busdata['rs'])
    if rspos:
      self.rf.setr(rspos, busdata['val'])
      self.regFile[rspos] = None

  def __repr__(self):
    headers = ['#', 'RF', 'RAT']
    table = remNone([[i, self.rf.getr(i), 'RS%d' % reg if reg is not None else reg] for (i, reg) in enumerate(self.regFile)])
    return tabulate(table, headers, tablefmt='fancy_grid')
  
  def __str__(self):
    return repr(self)


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
    self.endT = -1
    self.opcode = None
    self.res = None
    self.op1 = None
    self.op2 = None

  def execute(self, instr):
    [opcode, res, op1, op2] = instr
    self.endT = currT + self.functs[opcode]['t']
    self.opcode = opcode
    self.res = res
    self.op1 = op1
    self.op2 = op2
    return self.endT

  def isBusy(self):
    return self.endT < currT

  def broadcast(self, bus):
    if self.opcode is None:
      return
    if self.endT == currT:
      res = {
          'rs': self.res,
          'val': self.functs[self.opcode].funct(self.op1, self.op2)
      }
      bus.setb(res)


class ReserSt:

  def __init__(self, idx=None):
    fields = ['op', 'j', 'k', 'disp']
    self.content = {
      'idx': idx,
      'busy': 0,
      'disp': None,
    }
    self.t = {'issue': None, 'capture': None, 'dispatch': None}
    for field in fields:
      self.content[field] = None

  def setr(self, instr, rat):
    [opcode, res, op1, op2] = instr
    self.content['busy'] = 1
    self.content['op'] = opcode
    self.content['j'] = rat.getr(op1)
    self.content['k'] = rat.getr(op2)
    self.t['issue'] = currT
    rat.setr(res, self.content['idx'])

  def capture(self, busdata):
    if self.content['j'] == ('RAT', busdata['rs']):
      self.content['j'] = ('ABS', busdata['val'])
    if self.content['k'] == ('RAT', busdata['rs']):
      self.content['k'] = ('ABS', busdata['val'])

  def clear(self):
    self.__init__()

  def free(self):
    self.content['busy'] = 0

  def dispatch(self, alu):
    if self.content['j'][0] == 'ABS' and self.content['k'][
        0] == 'ABS' and self.t['issue'] != currT:
      self.content['disp'] = 1
      return (True,
              alu.execute([
                  self.content['op'], self.content['idx'], self.content['j'][1],
                  self.content['k'][1]
              ]))
    return (False, None)

  def getEntries(self):
    c = self.content
    v = {'j': None, 'k': None}
    q = {'j': None, 'k': None}
    for op in ['j', 'k']:
      if c[op]:
        if c[op][0] == 'RAT':
          q[op] = c[op][1]
        else:
          v[op] = c[op][1]
    
    return remNone(['RS%d' % c['idx'], c['busy'], v['j'], v['k'], q['j'], q['k'], c['disp']])


class ReserALU:

  def __init__(self, tag, size, functs, st=0):
    self.tag = tag
    self.size = size
    self.RS = [ReserSt(st + i) for i in range(size)]
    self.alu = ALU(functs)
    self.valid = [0] * self.size
    self.freed = [None] * self.size

  def getUsage(self):
    return [
        sum(x)
        for x in zip(self.valid, [1 if t == currT else 0 for t in self.freed])
    ]

  def getr(self, idx):
    return self.RS[idx]

  def setr(self, instr, rat):
    usage = self.getUsage()
    emppos = usage.index(0)
    self.RS[emppos].setr(instr, rat)
    self.valid[emppos] = 1

  def isFull(self):
    usage = self.getUsage()
    return sum(usage) >= self.size

  def capture(self, busdata):
    for RSi in self.RS:
      RSi.capture(busdata)

  def clear(self, idx):
    self.RS[idx].free()
    self.valid[idx] = 0
    self.freed[idx] = currT

  def dispatch(self):
    if not self.alu.isBusy():
      for RSi in self.RS:
        disp = RSi.dispatch(self.alu)
        if disp[0]:
          return disp
    return (False, None)

  def broadcast(self, bus):
    self.alu.broadcast(bus)

  def getEntries(self):
    return [x.getEntries() for x in self.RS]


class ReserStGrp:

  def __init__(self, rat, A=3, M=2):
    self.RG = {
        'A':
            ReserALU('A', A, [
                {
                    'opcode': 0,
                    'funct': (lambda x, y: x + y),
                    't': 2,
                },
                {
                    'opcode': 1,
                    'funct': (lambda x, y: x - y),
                    't': 2,
                },
            ]),
        'M':
            ReserALU('M', M, [
                {
                    'opcode': 2,
                    'funct': (lambda x, y: x * y),
                    't': 10,
                },
                {
                    'opcode': 3,
                    'funct': (lambda x, y: x / y),
                    't': 40
                },
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
    else:
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

  def dispatch(self):
    endTA = self.RG['A'].dispatch()
    endTM = self.RG['M'].dispatch()
    if endTA == endTM:
      self.RG['A'].alu.endT += 1

  def broadcast(self, bus):
    self.RG['A'].broadcast(bus)
    self.RG['M'].broadcast(bus)

  def __repr__(self):
    headers = ['RS', 'Busy', 'Op', 'Vj', 'Vk', 'Qj', 'Qk', 'Disp']
    table = []
    for t in self.types:
      table.extend(self.RG[t].getEntries())
    return tabulate(table, headers, tablefmt='fancy_grid')
  
  def __str__(self):
    return repr(self)


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

for currT in range(T + 1):
  print('\n\n @@@ CLOCK CYCLE = %d @@@\n\n' % currT)
  print(' ### RESERVATION STATION ###')
  print(rsg)
  print(' ### RAT ###')
  print(rat)
  print(' ### INSTRUCTION QUEUE ###')
  print(iq)
  # issue
  if not iq.isEmpty():
    instr = iq.peek()
    if not rsg.isFull(instr):
      rsg.setr(instr)
      iq.pop()

  # capture
  rsg.capture(bus)
  rat.clear(bus)

  # dispatch
  rsg.dispatch()

  # broadcast
  rsg.broadcast(bus)