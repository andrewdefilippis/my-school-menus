This implements an AWS Lambda function that uses the library and
the new `.calendar` calendar API to produce a caching ical generator for
any MSM menu that you request via the URL. It expects a Function URL.
The path elements are district/site/menu, and these can be integers
or strings. If strings, the lambda resolves them via the API using a
shortest initial lowercase match algorithm.

For example, I picked a random prefix from the MSM site and made a URL
that works:

    https://my-function-url/learning%20first/learning%20first/lunch

This resolves to the same as

    https://my-function-url/1952/12797/107925

They use the same cache, even. The cache is volatile and stored on the
lambda instance, but does help to keep load off the MSM server.

All months available are aggregated into a single feed, and the
`.calendar` interface puts a UID on each event so that any event changes
are synced on refresh.

For the my_school_menus dependecy management there is a `mkzip` tool to
construct a lambda layer. You can create this layer and add it to your
lambda. The layer zipfile is `lambda-layer.zip`, or you can specify an
alternate name with `-o`.

Alternatively, you can use `mkzip -f` to construct a full deployment
that does not depend on layers. In this case, all module dependencies
are bundled and you can upload the `lambda-deploy.zip` as a single
Lambda application zipfile.
