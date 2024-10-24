import { merge } from "webpack-merge";
import commonConfig from "./common.config";

// This variable should mirror the one from config/settings/production.py
const staticUrl = "/static/";

export default merge(commonConfig, {
	mode: "production",
	devtool: "source-map",
	bail: true,
	output: {
		publicPath: `${staticUrl}webpack_bundles/`,
	},
});
