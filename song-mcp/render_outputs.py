"""Optional human-readable outputs, using the isolated analyzer environment."""
import sys
from pathlib import Path
import allin1


if __name__=='__main__':
    directory=Path(sys.argv[1]); out=Path(sys.argv[2]); stem=sys.argv[3]
    result=allin1.load_result(directory/'music/original.json')
    if '--visualize' in sys.argv:
        allin1.visualize(result,out_dir=out/'viz',multiprocess=False)
        (out/'viz/original.pdf').replace(out/'viz'/f'{stem}.pdf')
    if '--sonify' in sys.argv:
        allin1.sonify(result,out_dir=out/'sonif',multiprocess=False)
        (out/'sonif/original.sonif.wav').replace(out/'sonif'/f'{stem}.sonif.wav')
