/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Acl

namespace NuropbRMQ.Acl

export NuropbRmq.Pattern.Acl (Perms matchesPrefix allowed canConfigure canPublish canRead
  replyPublishRestrictedClient replyPublishRestrictedService meshBindNamespaced)

end NuropbRMQ.Acl
