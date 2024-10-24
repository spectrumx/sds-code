import { resolve as _resolve, join } from "node:path";
import MiniCssExtractPlugin, {
	loader as _loader,
} from "mini-css-extract-plugin";
import BundleTracker from "webpack-bundle-tracker";

export const target = "web";
export const context = join(__dirname, "../");
export const entry = {
	project: _resolve(__dirname, "../sds_gateway/static/js/project"),
	vendors: _resolve(__dirname, "../sds_gateway/static/js/vendors"),
};
export const output = {
	path: _resolve(__dirname, "../sds_gateway/static/webpack_bundles/"),
	publicPath: "/static/webpack_bundles/",
	filename: "js/[name]-[fullhash].js",
	chunkFilename: "js/[name]-[hash].js",
};
export const plugins = [
	new BundleTracker({
		path: _resolve(join(__dirname, "../")),
		filename: "webpack-stats.json",
	}),
	new MiniCssExtractPlugin({ filename: "css/[name].[contenthash].css" }),
];
export const module = {
	rules: [
		// we pass the output from babel loader to react-hot loader
		{
			test: /\.js$/,
			loader: "babel-loader",
		},
		{
			test: /\.s?css$/i,
			use: [
				_loader,
				"css-loader",
				{
					loader: "postcss-loader",
					options: {
						postcssOptions: {
							plugins: ["postcss-preset-env", "autoprefixer", "pixrem"],
						},
					},
				},
				"sass-loader",
			],
		},
	],
};
export const resolve = {
	modules: ["node_modules"],
	extensions: [".js", ".jsx"],
};
