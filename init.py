#%%
import json
from collections import defaultdict

NREGS = 8
clin = lambda: input().strip()


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
    if busdata is None:
      return
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
    return self.endT < currT # TODO: account the condition when both the ALU produce result at the same time

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
        'valid': False,
        'busy': False,
    }
    self.t = {'issue': None, 'capture': None, 'dispatch': None}
    for field in fields:
      self.content[field] = None

  def setr(self, instr, rat):
    [opcode, res, op1, op2] = instr
    self.content['valid'] = True
    self.content['busy'] = True
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
    self.valid = False

  def dispatch(self, alu):
    if self.content['j'][0] == 'ABS' and self.content['k'][0] == 'ABS' and self.t['issue'] != currT:
      return (True, alu.execute([self.content['op'], self.content['idx'], self.content['j'][1], self.content['k'][1]]))
    return (False, None)

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

  def dispatch(self):
    if not self.alu.isBusy():
      for RSi in self.RS:
        disp = RSi.dispatch(self.alu)
        if disp[0]:
          return disp
    return (False, None)

  def broadcast(self, bus):
    self.alu.broadcast(bus)

  def __str__(self):
    return json.dumps(map(lambda x: x.content, self.RS))


class ReserStGrp:

  def __init__(self, rat, A=3, M=2):
    self.RG = {
        'A':
            ReserALU('M', M, [
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