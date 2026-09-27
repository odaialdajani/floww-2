// craco.config.js
const path = require("path");
require("dotenv").config();

const config = {
  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    cache: false,
    configure: (webpackConfig) => {
      webpackConfig.plugins = webpackConfig.plugins.filter(
        (p) =>
          p.constructor?.name !== "ForkTsCheckerWebpackPlugin" &&
          p.constructor?.name !== "ESLintWebpackPlugin"
      );
      webpackConfig.module.rules = webpackConfig.module.rules.map((rule) => {
        if (rule.use) {
          rule.use = rule.use.filter(
            (u) => !u.loader || !u.loader.includes("eslint-loader")
          );
        }
        return rule;
      });
      return webpackConfig;
    },
  },
  devServer: {
    hot: true,
    liveReload: true,
  },
  jest: {
    configure: {
      testEnvironment: "jsdom",
      moduleNameMapper: {
        "^@/(.*)$": "<rootDir>/src/$1",
        "\\.(css|less|scss|sass)$": "identity-obj-proxy",
        // jest-resolve (v27, via react-scripts 5) cannot resolve the
        // conditional "./is-development" export of @radix-ui/primitive
        // (node/webpack resolve it fine — production build unaffected).
        // Pin tests to the production variant: radix dev-warnings off.
        "^@radix-ui/primitive/is-development$":
          "<rootDir>/node_modules/@radix-ui/primitive/dist/internal/is-development.false.js",
      },
    },
  },
};

module.exports = config;
