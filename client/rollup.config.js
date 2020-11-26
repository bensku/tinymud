import typescript from '@rollup/plugin-typescript';

export default {
    input: 'src/init.ts',
    output: {
        dir: 'dist/app',
        sourcemap: true
    },
    plugins: [typescript()]
};