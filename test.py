import json
class A:
  def __init__(self, k):
    self.x = [k, k*2, None, False]
  
  def __repr__(self):
    return json.dumps(self.x)

class B:
  def __init__(self, k):
    self.a = A(k + 2)
    self.b = A(k + 5)
    self.x = {'a': self.a, 'b': self.b}
  
  def __repr__(self):
    return json.dumps({'a': repr(self.a), 'b': repr(self.b)})
  
  def __str__(self):
    return self.__repr__()

b = B(0)
print(b)
