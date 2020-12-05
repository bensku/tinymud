import typescript from '@rollup/plugin-typescript';
import { nodeResolve } from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';

export default {
    input: 'src/init.ts',
    output: {
        dir: 'dist/app',
        sourcemap: true
    },
    plugins: [typescript(), nodeResolve(), commonjs()]
};