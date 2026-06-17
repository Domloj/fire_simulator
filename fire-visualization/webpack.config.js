const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const webpack = require('webpack');
const Dotenv = require('dotenv-webpack');
const { EsbuildPlugin, ESBuildMinifyPlugin } = require('esbuild-loader');

module.exports = (env, argv) => {
  const isProduction = argv.mode === 'production';

  return {
    mode: isProduction ? 'production' : 'development',

    entry: './src/index.tsx',

    output: {
      filename: isProduction ? '[name].[contenthash].js' : '[name].js',
      chunkFilename: isProduction ? '[name].[contenthash].chunk.js' : '[name].chunk.js',
      path: path.resolve(__dirname, 'dist'),
      clean: true,
    },

    devtool: isProduction ? false : 'eval',

    cache: {
      type: 'filesystem',
      buildDependencies: {
        config: [__filename],
      },
    },

    devServer: {
      host: '0.0.0.0',
      port: process.env.FRONTEND_PORT || 8080,
      allowedHosts: 'all',
      hot: true,
      client: {
        logging: 'warn',
        overlay: false,
      },
      watchFiles: {
        paths: ['src/**/*'],
        options: { ignored: /node_modules/ },
      },
      devMiddleware: {
        stats: 'minimal',
      },
      proxy: [
        {
          context: ['/send-simulation-request'],
          target:
            process.env.FIRE_SIMULATION_SERVICE ||
            'http://fire-simulation-service:5000',
          changeOrigin: true,
          secure: false,
          pathRewrite: {
            '^/send-simulation-request': '/run_simulation',
          },
        },
      ],
    },

    resolve: {
      extensions: ['.tsx', '.ts', '.js'],
      alias: {
        '@shared': path.resolve(__dirname, 'src/shared/'),
        '@features': path.resolve(__dirname, 'src/features/'),
        '@app': path.resolve(__dirname, 'src/app/'),
      },
    },

    module: {
      rules: [
        {
          test: /\.m?js$/,
          resolve: { fullySpecified: false },
        },
        {
          test: /\.(ts|tsx)$/,
          exclude: /node_modules/,
          use: isProduction
            ? [
                {
                  loader: 'thread-loader',
                },
                {
                  loader: 'esbuild-loader',
                  options: {
                    loader: 'tsx',
                    target: 'es2018',
                  },
                },
              ]
            : [
                {
                  loader: 'esbuild-loader',
                  options: {
                    loader: 'tsx',
                    target: 'es2018',
                  },
                },
              ],
        },
        {
          test: /\.css$/i,
          use: ['style-loader', 'css-loader'],
        },
        {
          test: /\.(png|jpg|jpeg|gif|svg)$/i,
          type: 'asset/resource',
        },
      ],
    },

    optimization: isProduction
      ? {
          moduleIds: 'deterministic',
          runtimeChunk: 'single',
          splitChunks: {
            chunks: 'all',
            maxInitialRequests: 10,
            minSize: 30000,
          },
        }
      : {
          splitChunks: false,
          runtimeChunk: false,
        },

    plugins: [
      new HtmlWebpackPlugin({
        template: './src/index.html',
      }),

      new Dotenv({
        systemvars: true,
        silent: true,
        safe: true,
      }),

      new EsbuildPlugin(),

      new webpack.DefinePlugin({
        'process.env.NODE_ENV': JSON.stringify(
          isProduction ? 'production' : 'development'
        ),
        'import.meta.env.NODE_ENV': JSON.stringify(
          isProduction ? 'production' : 'development'
        ),
        'process.env.REACT_APP_VERSION': JSON.stringify(
          process.env.REACT_APP_VERSION || ''
        ),
      }),
    ],
  };
};
