import pickle, sys
sys.path.insert(0,'.')
import render
b = pickle.load(open('board.pkl','rb'))
render.render(b, '/tmp/claude-0/r_top.png', 'top')
render.render(b, '/tmp/claude-0/r_bot.png', 'bot')
probs = b.drc()
print("DRC problems:", len(probs))
for p in probs[:40]: print("  ", p)
con = b.connectivity()
bad = {n: g for n, g in con.items() if len(g) != 1}
print("nets:", len(con), "split nets:", len(bad))
for n, g in bad.items(): print("  ", n, g)
# nets that exist in pads but have no copper item at all (single pad nets are fine)
