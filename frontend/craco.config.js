// craco.config.js
const path = require("path");
require("dotenv").config();

const webpackConfig = {
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    cache: false,
    configure: (webpackConfig) => {
      webpackConfig.plugins = webpackConfig.plugins.filter(
        p => p.constructor?.name !== 'ForkTsCheckerWebpackPlugin' && p.constructor?.name !== 'ESLintWebpackPlugin'
      );
      webpackConfig.module.rules = webpackConfig.module.rules.map(rule => {
        if (rule.use) {
          rule.use = rule.use.filter(u => !u.loader || !u.loader.includes('eslint-loader'));
        }
        return rule;
      });
      return webpackConfig;
    },
  },
  devServer: {
    hot: true,
    liveReload: true,
    allowedHosts: "all",
    host: "0.0.0.0",
  },
};

module.exports = webpackConfig;
