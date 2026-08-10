/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as contributors from "../contributors.js";
import type * as http from "../http.js";
import type * as modelTraining from "../modelTraining.js";
import type * as modelTrainingValidators from "../modelTrainingValidators.js";
import type * as rateLimits from "../rateLimits.js";
import type * as reviewValidators from "../reviewValidators.js";
import type * as reviews from "../reviews.js";
import type * as searchTraining from "../searchTraining.js";
import type * as searchTrainingValidators from "../searchTrainingValidators.js";
import type * as training from "../training.js";
import type * as trainingValidators from "../trainingValidators.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  contributors: typeof contributors;
  http: typeof http;
  modelTraining: typeof modelTraining;
  modelTrainingValidators: typeof modelTrainingValidators;
  rateLimits: typeof rateLimits;
  reviewValidators: typeof reviewValidators;
  reviews: typeof reviews;
  searchTraining: typeof searchTraining;
  searchTrainingValidators: typeof searchTrainingValidators;
  training: typeof training;
  trainingValidators: typeof trainingValidators;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {};
