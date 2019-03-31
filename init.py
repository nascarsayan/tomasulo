# Copyright (C) by
# Sayan Naskar <nascarsayan@iitkgp.ac.in>
# Authors: Sayan Naskar <nascarsayan@gmail.com>
"""
Simulate the Tomasulo Algorithm.
Specifications: ./assgnSpec.pdf
"""
#%%
from tabulate import tabulate

NREGS = 8  # number of registers

clin = lambda: input().strip()
""" Returns the stripped version of input() """
remNone = lambda x: map(lambda y: '' if y is None or False else y, x)
""" Returns an array containing the elements of the input array 
except for 'None' elements which are converted to empty strings """


def printState(rsg, rat, iq):
  """Prints the current state of the hardware
  
  Parameters
  ----------
  rsg: The Reservation Station Group
  rat: The RAT table
  iq: The Instruction Queue
  """
  print(' ### RESERVATION STATION ###')
  print(rsg)
  print(' ### RAT ###')
  print(rat)
  print(' ### INSTRUCTION QUEUE ###')
  print(iq)


class InstrQ:
  """The Instruction Queue Class

  Fields
  ______
  queue: The list containing the instructions
  funcmap: The dict containg the opcode -> function-name mapping

  Methods
  -------
  push: Push an instruction into the queue
  pop: pop the oldest instruction from the queue
  peek: check the topmost instruction
  isEmpty: check if the queue is empty

  """

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
      row.extend(['R%d' % i for i in instr[1:]])
      table.append(row)
    return tabulate(table, headers, tablefmt='fancy_grid')

  def __str__(self):
    return repr(self)


class RF:
  """The Register File Class

  Fields
  ______
  size: The size of the register file
  regFile: The list containing the registers

  Methods
  -------
  setr: Set the value of a register
  getr: Get the value of a register

  """

  def __init__(self, size=8):
    self.size = size
    self.regFile = [None] * self.size

  def setr(self, idx, val):
    self.regFile[idx] = val

  def getr(self, idx):
    return self.regFile[idx]


class RAT:
  """The Register Alias Table

  Fields
  ______
  size: The size of the RAT
  regFile: The list containing the aliases to registers
  rf: The register file this RAT points to

  Methods
  -------
  setr: Set the value of a RAT cell
  getr: Get the value of a RAT cell
  clear: Clear the cells of RAT with alias matching with the broadcasted value 

  """

  def __init__(self, rf, size=8):
    self.size = size
    self.regFile = [None] * self.size
    self.rf = rf

  def setr(self, idx, val):
    self.regFile[idx] = val

  def getr(self, idx):
    ref = self.regFile[idx]
    if ref is not None:
      return ('RAT', ref)
    return ('ABS', self.rf.getr(idx))

  def clear(self, bus):
    busdata = bus.getb()
    if busdata['rs'] is None:
      return
    try:
      rspos = self.regFile.index(busdata['rs'])
      self.rf.setr(rspos, busdata['val'])
      self.regFile[rspos] = None
    finally:
      return

  def __repr__(self):
    headers = ['#', 'RF', 'RAT']
    table = [
        remNone([i,
                 self.rf.getr(i),
                 'RS%d' % reg if reg is not None else reg])
        for (i, reg) in enumerate(self.regFile)
    ]
    return tabulate(table, headers, tablefmt='fancy_grid')

  def __str__(self):
    return repr(self)


class Bus:
  """The Bus connecting the 2 ALUs to the RAT and Reservation Station Group

  Fields
  ______
  data: A dict specifying the tag and the value produced by the ALU

  Methods
  -------
  getb: Get the data present in the bus
  setb: Set the data present in the bus

  """

  def __init__(self):
    self.data = None
    self.reset()

  def reset(self):
    self.data = {'rs': None, 'val': None}

  def getb(self):
    return self.data

  def setb(self, data):
    self.data = data

  def __repr__(self):
    return tabulate([remNone([self.data['rs'], self.data['val']])],
                    ['RS', 'VAL'],
                    tablefmt='fancy_grid')

  def __str__(self):
    return repr(self)


class ALU:
  """The Computation Unit / Arithmetic-Logic Unit

  Fields
  ______
  functs: The functions performed by the ALU (an opcode -> operation mapping)
  endT: Time at which the execution is completed
  opcode: The code of the operation currently being executed
  res: The location where the result is to be stored
  op1: The location of operator 1
  op2: The location of operator 2

  Methods
  -------
  reset: Reset the ALU
  execute: Execute an operation
  isBusy: Check if the ALU is busy
  broadcast: Broadcast the output to the bus

  """

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
    # print('!!!!!!!! ALU exected till %d!!!!!!!\n' % self.endT)
    return self.endT

  def isBusy(self):
    return self.endT > currT

  def broadcast(self, bus):
    if self.opcode is None:
      return False
    if self.endT <= currT:
      res = {
          'rs': self.res,
          'val': self.functs[self.opcode]['funct'](self.op1, self.op2)
      }
      bus.setb(res)
      return True


class ReserSt:
  """The Reservation Station Unit

  Fields
  ______
  content: The content in the reservation station
  t: The time fields : issue

  Methods
  -------
  clear: Clear the contents of the reservation station
  setr: Issue an instruction into the reservation station
  capture: Capture the data from the bus into op1 and op2
  free: Tag the reservation station as invalid
  dispatch: Dispatch an instruction from the reservation station
  getEntries: Return the description of the reservation station in a list (row)

  """

  def __init__(self, idx=None):
    self.content = {
        'idx': idx,
    }
    self.t = {}
    self.clear()

  def clear(self):
    self.content['busy'] = 0
    cfields = ['disp', 'op', 'j', 'k']
    for field in cfields:
      self.content[field] = None
    tfields = ['issue']
    for field in tfields:
      self.t[field] = None

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

  def free(self):
    self.content['busy'] = 0

  def dispatch(self, alu):
    try:
      if self.content['j'][0] == 'ABS' and self.content['k'][
          0] == 'ABS' and self.t['issue'] != currT and (self.content['disp'] is
                                                        None):
        self.content['disp'] = currT
        return (True,
                alu.execute([
                    self.content['op'], self.content['idx'],
                    self.content['j'][1], self.content['k'][1]
                ]))
    finally:
      return (False, None)

  def getEntries(self):

    def rsAppend(v):
      if v is not None:
        return 'RS%d' % v
      return ''

    c = self.content
    v = {'j': None, 'k': None}
    q = {'j': None, 'k': None}
    for op in ['j', 'k']:
      if c[op] is not None:
        if c[op][0] == 'RAT':
          q[op] = c[op][1]
        else:
          v[op] = c[op][1]

    return remNone([
        'RS%d' % c['idx'], c['busy'], c['op'], v['j'], v['k'],
        rsAppend(q['j']),
        rsAppend(q['k']), c['disp']
    ])


class ReserALU:
  """A Reservation Station Group & the respective ALU group

  Fields
  ______
  tag: The tag of the Group : A -> Add M -> Mult
  size: The size of the group of reservation station
  RS: The list containing the group of Reservation Stations
  alu: The assigned ALU for the group
  valid: The list stating if an RS is busy or not
  freed: The list stating the latest time an RS has been freed

  Methods
  -------
  getUsage: An array contataing non-negative values:
            0 denotes it can be allocated at currT
  getr: Get the content of an RS
  set: Set the content of an RS
  isFull: Check if none of the RS in the group is available
  capture: Capture the bus value into each RS
  clear: Clear an RS
  dispatch: Dispatch an RS into the ALU
  brodcast: Broadcast the result of the ALU and the tag into the bus
  getEntries: Return the description of the RS in a list of rows

  """

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
    self.RS[idx].clear()
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
    return self.alu.broadcast(bus)

  def getEntries(self):
    return [x.getEntries() for x in self.RS]


class ReserStGrp:
  """The Group containg each type of Reservation Stations and their ALUs

  Fields
  ______
  RG: The collection of (RS groups + ALU) of various types
  types: The types of (RS groups + ALU) : A(ADD) and M(MULT)
  rat: The RAT the whole RG points to

  Methods
  -------
  getr: Get an RS by index
  setr: Set an RS by index
  isFull: Check if none of the RS in the group corresponding to the optype is available
  capture: Capture the bus value into each RS
  dispatch: Dispatch an RS into the ALU
  broadcast: Broadcast the result of an ALU and its tag into the bus
  
  """

  def __init__(self, rat, A=3, M=2):
    self.RG = {
        'A':
            ReserALU(
                'A', A, {
                    0: {
                        'funct': (lambda x, y: x + y),
                        't': 2,
                    },
                    1: {
                        'funct': (lambda x, y: x - y),
                        't': 2,
                    },
                }),
        'M':
            ReserALU(
                'M', M, {
                    2: {
                        'funct': (lambda x, y: x * y),
                        't': 10,
                    },
                    3: {
                        'funct': (lambda x, y: x / y),
                        't': 40
                    },
                }, A)
    }
    self.types = ['A', 'M']
    self.rat = rat

  def getr(self, idx):
    if idx >= 0 and idx <= self.RG['A'].size + self.RG['M'].size:
      if idx < self.RG['A'].size:
        return self.RG['A'].getr(idx)
      return self.RG['M'].getr(idx - self.RG['A'].size)

  def setr(self, instr):
    if instr[0] < 2:
      self.RG['A'].setr(instr, self.rat)
    else:
      self.RG['M'].setr(instr, self.rat)

  def isFull(self, instr):
    if instr[0] < 2:
      return self.RG['A'].isFull()
    return self.RG['M'].isFull()

  def capture(self, bus):
    busdata = bus.getb()
    if busdata['rs'] is not None:
      self.RG['A'].capture(busdata)
      self.RG['M'].capture(busdata)
      if busdata['rs'] < self.RG['A'].size:
        self.RG['A'].clear(busdata['rs'])
      else:
        self.RG['M'].clear(busdata['rs'] - self.RG['A'].size)

  def dispatch(self):
    endTA = self.RG['A'].dispatch()
    endTM = self.RG['M'].dispatch()
    if endTA[0] == True and endTA == endTM:
      self.RG['A'].alu.endT += 1

  def broadcast(self, bus):
    if not self.RG['M'].broadcast(bus):
      self.RG['A'].broadcast(bus)

  def __repr__(self):
    headers = ['RS#', 'Busy', 'Op', 'Vj', 'Vk', 'Qj', 'Qk', 'Disp (T)']
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

print('\n\n @@@ CLOCK CYCLE = 0 @@@\n\n')
printState(rsg, rat, iq)

for currT in range(1, T + 1):

  print('\n\n @@@ CLOCK CYCLE = %d @@@\n\n' % (currT))

  # issue
  if not iq.isEmpty():
    instr = iq.peek()
    if not rsg.isFull(instr):
      rsg.setr(instr)
      iq.pop()

  # broadcast
  bus.reset()
  rsg.broadcast(bus)

  # capture
  rsg.capture(bus)
  rat.clear(bus)

  # dispatch
  rsg.dispatch()

  printState(rsg, rat, iq)
