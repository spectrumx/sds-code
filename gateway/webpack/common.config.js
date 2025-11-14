// biome-ignore lint/style/useNodejsImportProtocol: <reason>
const path = require("path");
const BundleTracker = require("webpack-bundle-tracker");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

module.exports = {
	target: "web",
	context: path.join(__dirname, "../"),
	entry: {
		vendors: path.resolve(__dirname, "../sds_gateway/static/js/vendors"),
	},
	output: {
		path: path.resolve(__dirname, "../sds_gateway/static/webpack_bundles/"),
		publicPath: "/static/webpack_bundles/",
		filename: "js/[name]-[fullhash].js",
		chunkFilename: "js/[name]-[hash].js",
	},
	plugins: [
		new BundleTracker({
			path: path.resolve(path.join(__dirname, "../")),
			filename: "webpack-stats.json",
		}),
		new MiniCssExtractPlugin({ filename: "css/[name].[contenthash].css" }),
	],
	module: {
		rules: [
			// we pass the output from babel loader to react-hot loader
			{
				test: /\.js$/,
				loader: "babel-loader",
			},
			// CSS loader rule removed
		],
	},
	resolve: {
		modules: ["node_modules"],
		extensions: [".js", ".jsx"],
	},
};
