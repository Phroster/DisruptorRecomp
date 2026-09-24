"""Compile and exercise the actual renderer filter selector without a GL context.

The regression is a terrain triangle selecting the sprite filter when aligned
to the screen or missing PGXP positions. Checks the same draw class across
those states, plus sprite filtering and the existing opt-out/backdrop rules.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    renderer = (ROOT / 'psxrecomp/runtime/src/gpu_gl_renderer.c').read_text()
    start = renderer.index('static int smart_filter_mode(')
    end = renderer.index('\n}\n', start) + 3
    selector = renderer[start:end]
    harness = r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
static int enabled, s_pc_valid, s_pq_valid;
static float s_pq[3];
static int smart_filter_on(void) { return enabled; }
SELECTOR
int main(void) {
    const int xs[][3] = {{0,16,0}, {0,16,4}, {-64,384,32}, {0,0,0}};
    const int ys[][3] = {{0,0,16}, {0,3,17}, {-64,64,256}, {0,0,0}};
    unsigned checks = 0;
    for (enabled = 0; enabled <= 1; enabled++)
    for (int shape = 0; shape < 4; shape++)
    for (s_pc_valid = 0; s_pc_valid <= 1; s_pc_valid++)
    for (s_pq_valid = 0; s_pq_valid <= 1; s_pq_valid++)
    for (int equal = 0; equal <= 1; equal++)
    for (int depth = 0; depth <= 2; depth++)
    for (int backdrop = 0; backdrop <= 1; backdrop++) {
        s_pq[0] = 1.0f; s_pq[1] = equal ? 1.0f : 0.5f; s_pq[2] = 1.0f;
        /* World draw class must not change filters as projected shape or
         * precision tracking changes. Degenerate/clipped cases included. */
        assert(smart_filter_mode(xs[shape], ys[shape], depth, backdrop, 1)
               == (enabled ? 1 : 0));
        checks++;
        if (!enabled || depth == 2 || backdrop) {
            for (int kind = 0; kind <= 2; kind++) {
                assert(smart_filter_mode(xs[shape], ys[shape], depth, backdrop, kind)
                       == (enabled ? 1 : 0));
                checks++;
            }
        }
    }
    enabled = 1; s_pq_valid = 0;
    for (s_pc_valid = 0; s_pc_valid <= 1; s_pc_valid++) {
        /* Screen-aligned paletted sprites and rectangles retain xBR. */
        assert(smart_filter_mode(xs[0], ys[0], 0, 0, 0) == 2);
        assert(smart_filter_mode(xs[0], ys[0], 1, 0, 2) == 2);
        checks += 2;
    }
    puts("Terrain filter selection and sprite/opt-out rules passed.");
    printf("%u checks\n", checks);
    return 0;
}
'''.replace('SELECTOR', selector)
    (ROOT / 'logs').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='filter-selector-', dir=ROOT / 'logs') as directory:
        source = Path(directory) / 'selector.c'
        binary = Path(directory) / 'selector.exe'
        source.write_text(harness)
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
